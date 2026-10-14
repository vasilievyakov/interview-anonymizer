"""Put labels in place of sensitive spans.

Two passes over the original text:

1. Detector spans: every `Merged` span (not ignored) is resolved to a vault
   entity and replaced with its label.
2. Literal pass: strings the human added in review (`vault.added`) and every
   known variant or canonical of every vault entity are searched literally in
   what is left (case-insensitive, word-boundary, longest first). This catches
   repeats the detectors missed.

All replacements are computed as offsets into the original text and applied
right to left, so offsets stay valid and labels never get re-matched.
"""

from __future__ import annotations

import re
from functools import lru_cache

from . import names
from .model import LABEL_TAGS, Kind, Merged
from .vault import Entity, Vault, fold

# Literal-pass candidates shorter than this are too risky ("Ли", "ИП").
MIN_LITERAL_LEN = 3

# Labels that may already sit in the input (re-anonymizing a file): never touched.
_ALL_TAGS = sorted(
    {t for tags in LABEL_TAGS.values() for t in tags.values()}, key=len, reverse=True
)
_LABEL_RE = re.compile(r"\[(?:" + "|".join(map(re.escape, _ALL_TAGS)) + r")_\d+\]")

# Letters and digits only: "_" and punctuation count as boundaries.
_WB_BEFORE = r"(?<![^\W_])"
_WB_AFTER = r"(?![^\W_])"
_QUOTES = "«»\"“”„'"

_NAME_KINDS = {Kind.PERSON, Kind.ORG, Kind.LOCATION}


def _label_lang(lang: str) -> str:
    return lang if lang in LABEL_TAGS else "ru"


def _title(s: str) -> str:
    return re.sub(r"[^\W\d_]+", lambda m: m.group(0)[:1].upper() + m.group(0)[1:], s)


def _display(kind: Kind, text: str, normal: str) -> str:
    """Canonical form for restore.

    Person names: nominative of the surface as written (gender kept, no new "ё").
    Other kinds: the surface itself, so restore gives back exactly what was in the source
    (a phone stays "+7 912 345-67-89", not its digits-only normal).
    """
    if kind == Kind.PERSON:
        return names.nominative(text)
    return text


def _token_count(s: str) -> int:
    return len(names.name_key(s).split())


def _only_person_with_first_name(vault: Vault, text: str) -> Entity | None:
    """A lone first name ("Dave", "Марией", "Маша") joins the one known full name that has it.

    `names.same_person` never glues a lone first name: in general "Мария" is too
    common. Inside one project it usually is the same person, so it joins when
    exactly one known person carries that first name, and stays apart otherwise.
    """
    toks = [t for t in names.analyze(text) if t.role != names.INITIAL]
    if len(toks) != 1:
        return None
    lone = toks[0]
    found = []
    for e in vault.entities:
        if e.kind != Kind.PERSON:
            continue
        full = [t for t in names.analyze(e.canonical) if t.role != names.INITIAL]
        if len(full) < 2:
            continue
        # The given name: a token parsed as a first name, or the first token of a Latin name.
        firsts = [t.key for t in full if t.role == names.FIRST] or (
            [full[0].key] if full[0].role == names.OTHER else []
        )
        if lone.role in (names.FIRST, names.OTHER) and names.first_name_forms(lone.key) & set(firsts):
            found.append(e)
    return found[0] if len(found) == 1 else None


def _resolve_person(vault: Vault, text: str, normal: str) -> Entity:
    key_text = normal or text
    display = _display(Kind.PERSON, text, normal)
    e = vault.find(Kind.PERSON, text, normal)
    if e is None:
        matches = [
            x
            for x in vault.entities
            if x.kind == Kind.PERSON and names.same_person(key_text, x.canonical)
        ]
        if len(matches) == 1:
            e = matches[0]
    if e is None:
        e = _only_person_with_first_name(vault, key_text)
    if e is None:
        e = vault.get_or_create(Kind.PERSON, text, normal, canonical=display)
    elif _token_count(key_text) > _token_count(e.canonical) and names.same_person(
        key_text, e.canonical
    ):
        # A fuller form of a known name ("Мария Ковалева" after "Ковалева").
        e.canonical = display
    e.variants.add(fold(text))
    if normal:
        e.variants.add(fold(normal))
    return e


def _resolve(vault: Vault, kind: Kind, text: str, normal: str) -> Entity:
    if kind == Kind.PERSON:
        return _resolve_person(vault, text, normal)
    return vault.get_or_create(
        kind, text, normal, canonical=_display(kind, text, normal)
    )


def _literal_pattern(folded: str) -> re.Pattern[str]:
    """Regex matching any surface whose fold() equals `folded`."""
    parts: list[str] = []
    for ch in folded:
        if ch == "е":
            parts.append("[её]")
        elif ch == '"':
            parts.append("[" + re.escape(_QUOTES) + "]")
        elif ch.isspace():
            parts.append(r"\s+")
        else:
            parts.append(re.escape(ch))
    return re.compile(_WB_BEFORE + "".join(parts) + _WB_AFTER, re.IGNORECASE)


def _free(mask: bytearray, start: int, end: int) -> bool:
    return not any(mask[start:end])


def _take(mask: bytearray, start: int, end: int) -> None:
    mask[start:end] = b"\x01" * (end - start)


def _candidates(vault: Vault) -> dict[str, Entity | tuple[str, Kind]]:
    """Strings to search literally: hand-added values and every variant of every entity."""
    candidates: dict[str, Entity | tuple[str, Kind]] = {}
    for surface, kind in vault.added:
        f = fold(surface)
        if f:
            candidates.setdefault(f, (surface, kind))
    for e in vault.entities:
        for v in [fold(e.canonical), *sorted(e.variants)]:
            if len(v) >= MIN_LITERAL_LEN and v not in vault.ignored:
                existing = candidates.get(v)
                if existing is None or (
                    isinstance(existing, tuple) and existing[1] == e.kind
                ):
                    candidates[v] = e
    return candidates


def _plain_word(w: str) -> bool:
    from .detect.ner import _plain_word as plain

    return plain(w)


def _ordinary_lowercase(s: str) -> bool:
    """A lowercase dictionary word ("работу", "корзина") is speech, not the name found elsewhere.

    A name repeated in lowercase by speech-to-text ("ковалева перезвонила") is not
    a dictionary word and is still replaced.
    """
    from .detect.ner import _plain_word

    return s.islower() and " " not in s.strip() and _plain_word(s)


def _literal(
    text: str,
    mask: bytearray,
    vault: Vault,
    candidates: dict[str, Entity | tuple[str, Kind]],
    hits: list[tuple[int, int, Entity]],
) -> None:
    """Replace every free literal occurrence of the candidates, longest first."""
    for folded in sorted(candidates, key=lambda f: (-len(f), f)):
        target = candidates[folded]
        for m in _literal_pattern(folded).finditer(text):
            if not _free(mask, m.start(), m.end()):
                continue
            if _ordinary_lowercase(m.group(0)):
                continue
            if isinstance(target, tuple):
                surface, kind = target
                target = _resolve(vault, kind, m.group(0), surface)
                candidates[folded] = target
            else:
                target.variants.add(fold(m.group(0)))
            hits.append((m.start(), m.end(), target))
            _take(mask, m.start(), m.end())


def plan(text: str, spans: list[Merged], vault: Vault) -> list[tuple[int, int, Entity]]:
    """Where labels go: (start, end, entity) in the original text, sorted by start."""
    mask = bytearray(len(text))
    for m in _LABEL_RE.finditer(text):
        _take(mask, m.start(), m.end())

    hits: list[tuple[int, int, Entity]] = []

    # Pass 1: multi-word names, known from earlier files or from a table column of
    # this text, before any detector span: "Лисицына Ольга" from a table must win
    # over a lone "Ольга" found by NER inside "Лисицына Ольга, 37" further down.
    # Only trusted spans (table columns) join here: an NER span may be wrong
    # ("Звонила Ковалева") and must not spread to every repeat.
    multi = {f: t for f, t in _candidates(vault).items() if isinstance(t, Entity)}
    for s in sorted(spans, key=lambda s: s.start):
        f = fold(s.text)
        if " " in f and "column" in s.sources and not vault.is_ignored(s.text) and f not in multi:
            multi[f] = _resolve(vault, s.kind, s.text, s.normal)
    _literal(text, mask, vault, {f: t for f, t in multi.items() if " " in f}, hits)

    # Pass 2: detector spans. Defensive against overlaps and bad offsets.
    for s in sorted(spans, key=lambda s: (s.start, -(s.end - s.start))):
        if not (0 <= s.start < s.end <= len(text)):
            continue
        if not _free(mask, s.start, s.end):
            continue
        if vault.is_ignored(s.text):
            continue
        e = _resolve(vault, s.kind, s.text, s.normal)
        hits.append((s.start, s.end, e))
        _take(mask, s.start, s.end)

    # Pass 3: every known string literally, longest first.
    _literal(text, mask, vault, _candidates(vault), hits)

    # Pass 4: other grammatical forms of known names ("Ветру" after "Ветер").
    hits.extend(_form_hits(text, mask, vault))

    hits.sort(key=lambda h: h[0])
    return hits


_CYR_WORD = re.compile(r"[А-Яа-яЁё]+(?:-[А-Яа-яЁё]+)*")
# Pass 3 only reads forms of names this long; shorter ones collide with ordinary words.
MIN_FORM_LEN = 4


@lru_cache(maxsize=50000)
def _lemmas(word: str) -> frozenset[str]:
    """Every dictionary form a Cyrillic word can come from, folded.

    Plural readings are left out: "Ромашками пахнет" is flowers, not the company
    "Ромашка", and a person is never plural.
    """
    low = word.lower().replace("ё", "е")
    out = {low, names.name_key(low)}
    for p in names.morph_vocab().parse(low):
        if p.tag.number == "plur" and "Pltm" not in p.tag:
            continue
        out.add(p.normal_form.replace("ё", "е"))
    return frozenset(out)


def _lemma(word: str, kind: Kind) -> str:
    """The one dictionary form a known name's word is filed under."""
    low = word.lower().replace("ё", "е")
    if kind == Kind.PERSON:
        return names.name_key(low)
    parses = names.morph_vocab().parse(low)
    return parses[0].normal_form.replace("ё", "е") if parses else low


def _form_hits(text: str, mask: bytearray, vault: Vault) -> list[tuple[int, int, Entity]]:
    """Word sequences whose lemmas match a known name's lemmas.

    Only Cyrillic names of PERSON / ORG / LOCATION entities. A single word must
    be capitalised in the text, so ordinary lowercase speech stays as it is.
    """
    keys: dict[tuple[str, ...], Entity] = {}
    for e in vault.entities:
        if e.kind not in _NAME_KINDS:
            continue
        for v in {fold(e.canonical), *e.variants}:
            if v in vault.ignored:
                continue
            words = v.split()
            if not words or not all(_CYR_WORD.fullmatch(w) for w in words):
                continue
            if len(words) == 1 and len(words[0]) < MIN_FORM_LEN:
                continue
            keys.setdefault(tuple(_lemma(w, e.kind) for w in words), e)
            if e.kind == Kind.PERSON and 1 < len(words) <= 3:
                # A surname on its own: "Лисицына" after "Лисицына Ольга". Only for
                # names of two or three words, and never an ordinary dictionary word:
                # a span that ran on into speech must not turn "Говорит" into a name.
                toks = names.analyze(v)
                if any(t.role == names.FIRST for t in toks):
                    for t, w in zip(toks, words):
                        if (
                            t.role in (names.SURN, names.OTHER)
                            and len(w) >= MIN_FORM_LEN
                            and not _plain_word(w)
                        ):
                            keys.setdefault((_lemma(w, e.kind),), e)
    if not keys:
        return []
    by_first: dict[str, list[tuple[tuple[str, ...], Entity]]] = {}
    for key, e in keys.items():
        by_first.setdefault(key[0], []).append((key, e))
    longest = max(len(k) for k in keys)
    tokens = [m for m in _CYR_WORD.finditer(text)]
    hits: list[tuple[int, int, Entity]] = []
    i = 0
    while i < len(tokens):
        matched = 0
        for n in range(min(longest, len(tokens) - i), 0, -1):
            seq = tokens[i : i + n]
            # Words of one name: separated by spaces only. A single word must be
            # capitalised; a sequence ("северному ветру") is specific enough without it.
            if any(text[a.end() : b.start()].strip() for a, b in zip(seq, seq[1:])):
                continue
            if n == 1 and not seq[0].group(0)[:1].isupper():
                continue
            a, b = seq[0].start(), seq[-1].end()
            if not _free(mask, a, b):
                continue
            first = _lemmas(seq[0].group(0))
            cands = [c for lem in first for c in by_first.get(lem, ())]
            for key, e in cands:
                if len(key) == n and all(k in _lemmas(m.group(0)) for k, m in zip(key, seq)):
                    if vault.is_ignored(text[a:b]):
                        break
                    hits.append((a, b, e))
                    e.variants.add(fold(text[a:b]))
                    _take(mask, a, b)
                    matched = n
                    break
            if matched:
                break
        i += matched or 1
    return hits


def apply_with_report(
    text: str, spans: list[Merged], vault: Vault, lang: str
) -> tuple[str, list[tuple[str, str]]]:
    """Replace sensitive spans with labels.

    Returns the new text and (label, original surface) pairs in text order.
    """
    lang = _label_lang(lang)
    hits = plan(text, spans, vault)
    report = [(vault.label(e, lang), text[a:b]) for a, b, e in hits]
    out = text
    for a, b, e in reversed(hits):
        out = out[:a] + vault.label(e, lang) + out[b:]
    return out, report


def apply(text: str, spans: list[Merged], vault: Vault, lang: str) -> str:
    """Replace sensitive spans with labels; see `apply_with_report`."""
    return apply_with_report(text, spans, vault, lang)[0]
