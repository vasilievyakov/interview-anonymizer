"""Named entities (PERSON / ORG / LOCATION) from natasha and spaCy.

Natasha runs for Russian only; spaCy uses ru_core_news_sm for Russian and
en_core_web_sm for English. Models load lazily, once per process.

Long transcripts are processed in chunks cut at blank lines (or, for very long
paragraphs, at line breaks, sentence ends or spaces); offsets always refer to
the original text.
"""

from __future__ import annotations

import re
import warnings
from collections.abc import Iterable, Iterator
from contextlib import contextmanager

from ..model import Finding, Kind
from ..names import morph_vocab

NER_LAYERS = ("natasha", "spacy")

# Chunk size in characters. Natasha and spaCy both work sentence by sentence,
# so this only bounds memory and per-call overhead.
CHUNK = 4000

_LABELS = {
    "PER": Kind.PERSON,
    "PERSON": Kind.PERSON,
    "ORG": Kind.ORG,
    "LOC": Kind.LOCATION,
    "GPE": Kind.LOCATION,
}

_SPACY_MODELS = {"ru": "ru_core_news_sm", "en": "en_core_web_sm"}
# Components not needed for NER (ru keeps the lemmatizer for `normal`).
_SPACY_EXCLUDE = {
    "ru": ["parser"],
    "en": ["parser", "tagger", "attribute_ruler", "lemmatizer"],
}

_models: dict[str, object] = {}

# Characters stripped from both ends of a span. Quotes and the period after an
# initial are handled separately.
_STRIP = set(" \t\r\n ,;:!?()[]{}<>—–-…*_/\\|·•")
# Typographic quote pairs (opening, closing).
_QUOTES = (("«", "»"), ("„", "“"))

# Conversational filler that small models sometimes tag as entities when it
# opens a sentence. Compared case-insensitively against the whole span.
_FILLER = {
    "ну",
    "короче",
    "типа",
    "вот",
    "да",
    "нет",
    "ага",
    "угу",
    "слушай",
    "смотри",
    "блин",
    "окей",
    "ок",
    "спасибо",
    "привет",
    "здравствуйте",
    "yeah",
    "yes",
    "no",
    "okay",
    "ok",
    "um",
    "uh",
    "hmm",
    "well",
    "so",
    "like",
    "right",
    "thanks",
}


# ---- models ---------------------------------------------------------------


@contextmanager
def _quiet():
    """Silence the pymorphy2 pkg_resources warning and friends while loading."""
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message=".*pkg_resources.*")
        warnings.filterwarnings("ignore", category=DeprecationWarning)
        warnings.filterwarnings("ignore", category=UserWarning, module="pymorphy2.*")
        yield


def _natasha():
    m = _models.get("natasha")
    if m is None:
        with _quiet():
            from natasha import NewsEmbedding, NewsMorphTagger, NewsNERTagger, Segmenter

            emb = NewsEmbedding()
            m = (Segmenter(), NewsMorphTagger(emb), NewsNERTagger(emb), morph_vocab())
        _models["natasha"] = m
    return m


def _spacy(lang: str):
    key = f"spacy:{lang}"
    m = _models.get(key)
    if m is None:
        with _quiet():
            import spacy

            m = spacy.load(_SPACY_MODELS[lang], exclude=_SPACY_EXCLUDE[lang])
        _models[key] = m
    return m


# ---- chunking -------------------------------------------------------------


def _cut(text: str, start: int, end: int, limit: int) -> Iterator[tuple[int, int]]:
    """Split text[start:end] into pieces of at most ~limit chars at the best boundary."""
    while end - start > limit:
        window = text[start : start + limit]
        cut = -1
        for pattern in (r"\n[ \t]*\n", r"\n", r"[.!?…]\s", r"\s"):
            hits = [m.end() for m in re.finditer(pattern, window)]
            hits = [h for h in hits if h > limit // 4]
            if hits:
                cut = hits[-1]
                break
        if cut <= 0:
            cut = limit
        yield start, start + cut
        start += cut
    if end > start:
        yield start, end


def chunks(text: str, limit: int = CHUNK) -> list[tuple[int, str]]:
    """(offset, piece) pairs covering text, cut at blank lines where possible."""
    out: list[tuple[int, str]] = []
    pos = 0
    pieces: list[tuple[int, int]] = []
    for m in re.finditer(r"\n[ \t]*\n\s*", text):
        pieces.append((pos, m.start()))
        pos = m.end()
    pieces.append((pos, len(text)))
    # Pack paragraphs into chunks up to `limit`; split oversize paragraphs.
    cur_s = cur_e = None
    for s, e in pieces:
        if e <= s:
            continue
        if e - s > limit:
            if cur_s is not None:
                out.append((cur_s, text[cur_s:cur_e]))
                cur_s = cur_e = None
            for a, b in _cut(text, s, e, limit):
                out.append((a, text[a:b]))
            continue
        if cur_s is not None and e - cur_s > limit:
            out.append((cur_s, text[cur_s:cur_e]))
            cur_s = None
        if cur_s is None:
            cur_s = s
        cur_e = e
    if cur_s is not None:
        out.append((cur_s, text[cur_s:cur_e]))
    return out


# ---- span cleanup ---------------------------------------------------------


def _is_initial_dot(text: str, i: int) -> bool:
    """text[i] == '.' closes an initial like "М." or "А." in "Ковалева М.А."."""
    if i < 1 or not text[i - 1].isalpha() or not text[i - 1].isupper():
        return False
    return i < 2 or not text[i - 2].isalpha()


def fix_span(text: str, start: int, end: int) -> tuple[int, int]:
    """Trim punctuation and whitespace from a span and balance its quotes.

    Natasha drops the closing quote of ORG names: `ООО «Северный ветер` ->
    `ООО «Северный ветер»` when the closing quote immediately follows.
    """
    for _ in range(4):
        before = (start, end)
        while start < end and text[start] in _STRIP:
            start += 1
        while start < end and (
            text[end - 1] in _STRIP
            or (text[end - 1] == "." and not _is_initial_dot(text, end - 1))
        ):
            end -= 1
        # English possessive: "John's" -> "John".
        if end - start > 2 and text[end - 2 : end] in ("'s", "’s"):
            end -= 2
        span = text[start:end]
        # Typographic quotes.
        for op, cl in _QUOTES:
            n_open, n_close = span.count(op), span.count(cl)
            if n_open > n_close:
                if end < len(text) and text[end] == cl:
                    end += 1
                elif span.startswith(op):
                    start += 1
            elif n_close > n_open and span.endswith(cl):
                end -= 1
            span = text[start:end]
        # Straight quotes.
        if span.count('"') % 2 == 1:
            if end < len(text) and text[end] == '"' and not span.endswith('"'):
                end += 1
            elif span.startswith('"'):
                start += 1
            elif span.endswith('"'):
                end -= 1
        if (start, end) == before:
            break
    return start, end


def _balance_normal(normal: str) -> str:
    """Apply the same quote balancing to a normal form."""
    normal = normal.strip("".join(_STRIP))
    for op, cl in _QUOTES:
        if normal.count(op) > normal.count(cl):
            normal += cl
    if normal.count('"') % 2 == 1:
        normal += '"'
    return normal


# Generic abbreviations NER tags as organisations: legal forms, document names,
# job functions, technologies. Compared case-insensitively per word; a hyphenated
# ending is ignored ("HR-ом").
_GENERIC = {
    "ооо", "ао", "пао", "зао", "оао", "ип", "нко", "гуп", "муп", "фгуп",
    "снилс", "инн", "огрн", "кпп", "бик", "гпх", "ндфл", "ндс", "пп",
    "рф", "мфц", "тц", "бц", "жк", "вуз", "сво", "снг",
    "hr", "it", "ит", "ии", "ai", "smm", "crm", "erp", "sku", "mlm", "nps", "kpi", "okr",
    "qa", "ux", "ui", "pr", "seo", "b2b", "b2c", "llc", "ltd", "inc", "plc", "us", "uk",
    "кадры", "отдел кадров", "инт", "дмс", "омс",
}
# Speaker roles in transcripts: "Интервьюер:", "Respondent:".
_ROLES = {
    "интервьюер",
    "респондент",
    "модератор",
    "ведущий",
    "ведущая",
    "спикер",
    "собеседник",
    "участник",
    "interviewer",
    "respondent",
    "moderator",
    "host",
    "speaker",
    "participant",
}

# Parts of speech that never form a name on their own (pymorphy2 tags).
_FUNCTION_POS = {"NPRO", "PREP", "CONJ", "PRCL", "INTJ"}
_PROPER = ("Name", "Surn", "Patr", "Geox", "Orgn", "Trad", "Abbr")
_WORD = re.compile(r"[^\W\d_]+(?:-[^\W\d_]+)*")


def _nounish(word: str) -> float:
    """Share of pymorphy2 parses of a Cyrillic word that could be part of a name."""
    total = 0.0
    for p in morph_vocab().parse(word.lower()):
        tag = p.tag
        if tag.POS == "NOUN" or any(g in tag for g in _PROPER) or "UNKN" in tag:
            total += p.score
    return total


def _function_word(word: str) -> bool:
    if not word.islower():
        return False
    parses = morph_vocab().parse(word)
    return bool(parses) and parses[0].tag.POS in _FUNCTION_POS and parses[0].score > 0.5


def _trim_words(text: str, start: int, end: int) -> tuple[int, int]:
    """Drop pronouns, prepositions, particles, verbs and fillers at span edges (ru).

    spaCy sometimes swallows a neighbour: "Тинькофф мне" -> "Тинькофф".
    """
    words = [(m.start() + start, m.end() + start) for m in _WORD.finditer(text[start:end])]

    def edge(w: tuple[int, int]) -> bool:
        word = text[w[0] : w[1]]
        low = word.lower()
        # Case-insensitive: speech-to-text capitalises "И", "Про", "Через" at phrase starts.
        return _function_word(low) or low in _FILLER or _verbish(word)

    def tail(w: tuple[int, int]) -> bool:
        # A trailing abbreviation is speech or an id prefix ("Эльвире Инт"); a leading
        # one is a legal form and belongs to the name ("ООО «Северный ветер»").
        low = text[w[0] : w[1]].lower().replace("ё", "е")
        return edge(w) or low.split("-")[0] in _GENERIC

    while len(words) > 1 and tail(words[-1]):
        words.pop()
        end = words[-1][1]
    while len(words) > 1 and edge(words[0]):
        words.pop(0)
        start = words[0][0]
    return start, end


_VERB_POS = {"VERB", "INFN", "GRND", "PRTS", "ADVB", "PRED", "COMP"}


def _verbish(word: str) -> bool:
    """A verb or adverb at a span edge: "Звонила Ковалевой", "Расскажите Ирина"."""
    if not re.search("[а-яё]", word.lower()):
        return False
    parses = morph_vocab().parse(word.lower())
    if not parses or any(g in p.tag for p in parses for g in ("Name", "Surn", "Patr")):
        return False
    return parses[0].tag.POS in _VERB_POS and parses[0].score > 0.5


def _plain_word(word: str) -> bool:
    """A dictionary word with no name-like reading: "Мясо", "Сводка", "Да".

    Transcripts written by speech-to-text capitalise phrase starts without
    punctuation, so NER tags such words as names. Words the dictionary does not
    know ("Гульнара" is known as a name, a rare surname is not known at all) are
    never plain.
    """
    if not re.search("[а-яё]", word.lower()):
        return False
    parses = morph_vocab().parse(word.lower())
    if not parses:
        return False
    for p in parses:
        # Only whole dictionary words: "Телзет" parsed as prefix + "зет" is not one.
        if len(p.methods_stack) != 1 or type(p.methods_stack[0][0]).__name__ != "DictionaryAnalyzer":
            return False
        if any(g in p.tag for g in _PROPER):
            return False
    return True


def _bad(span: str, kind: Kind, lang: str) -> bool:
    letters = [c for c in span if c.isalpha()]
    if len(span) < 2 or len(letters) < 2:
        return True
    low = span.lower().replace("ё", "е")
    if low in _FILLER or low in _ROLES:
        return True
    if kind == Kind.PERSON and lang == "en" and not any(c.isupper() for c in span):
        return True
    words = _WORD.findall(span)
    if words and words[0].lower() in _ROLES:
        return True  # "Speaker A", "Респондент 2"
    if words and all(w.lower().replace("ё", "е").split("-")[0] in _GENERIC for w in words):
        return True  # "HR", "ИП", "HR-ом"
    if re.fullmatch(r"(?i)инт\.?\s?\d+\S*", span.strip()):
        return True  # interview ids ("Инт.12_Hs5nJd") stay in the text by design
    if lang == "ru" and len(words) == 1 and len(words[0]) <= 3 and re.search("[а-яё]", low):
        # "Ли", "Сто" opening a phrase in speech-to-text: a particle or a number first.
        parses = morph_vocab().parse(low)
        if parses and parses[0].tag.POS in _FUNCTION_POS | {"NUMR", "PRED", "ADVB"}:
            return True
    if lang == "ru":
        # Every word an ordinary dictionary word: "Вот Салат", "Карьера".
        # Places are only filtered as single words: "Красная площадь" is ordinary words too.
        if (kind == Kind.PERSON or (kind == Kind.LOCATION and len(words) == 1)) and words and all(
            _plain_word(w) for w in words
        ):
            return True
        # A single Russian word that can only be a verb, adverb, particle and so on:
        # "Расскажите", "Значит" at the start of a sentence.
        if len(words) == 1 and re.search("[а-яё]", low) and _nounish(words[0]) < 0.1:
            return True
    return False


# Places where a NER span must not continue: line breaks, brackets, colons,
# sentence ends, " - ". Transcript headers glue a name to its speaker tag:
# "Олег (Speaker B): Да" or "0:12:30 - Олег".
_SEP = re.compile(r"\n|[()\[\]|:;]|[.!?…](?=\s)|\s[-–—]\s")


# Ordinary dictionary words written with a capital letter inside a phrase (not
# after . ! ? : or a line break). In edited text this almost never happens; names
# do not count, so a text dense with names is not noisy. Speech-to-text that
# capitalises every phrase without punctuation gives one such word in ten and more.
_MIDWORD = re.compile(r"[^\W\d_],?[ \t]+([А-ЯЁ][а-яё]+)")
_CYR_WORDS = re.compile(r"[А-Яа-яЁё]+")
NOISY_CAPITALS = 0.06


def noisy_capitals(piece: str) -> bool:
    """True when capital letters in this piece of text carry no information."""
    words = len(_CYR_WORDS.findall(piece))
    if words < 40:
        return False
    plain = sum(1 for w in _MIDWORD.findall(piece) if _plain_word(w))
    return plain / words > NOISY_CAPITALS


def _finding(
    text: str,
    start: int,
    end: int,
    kind: Kind,
    source: str,
    normal: str,
    lang: str,
    noisy: bool = False,
) -> Finding | None:
    cuts = [(m.start() + start, m.end() + start) for m in _SEP.finditer(text[start:end])]
    if cuts:
        # The span crosses a boundary: keep the first piece that is a name by itself.
        bounds = [start] + [x for c in cuts for x in c] + [end]
        for a, b in zip(bounds[::2], bounds[1::2]):
            if b > a:
                f = _finding_piece(text, a, b, kind, source, "", lang, noisy)
                if f:
                    return f
        return None
    return _finding_piece(text, start, end, kind, source, normal, lang, noisy)


_ADJ_POS = {"ADJF", "ADJS", "COMP"}


def _cut_tail(text: str, start: int, end: int, kind: Kind) -> int:
    """End of the name part of a span that ran on into speech.

    Speech-to-text capitalises every phrase, so NER glues a name to what follows:
    "Зоя Петровна Говорит Что У Ритмо", "ООО Северный Ключ Это Типа Оптовая".
    A name stops at the first verb, function word or filler after it (for companies
    and places only a capitalised one: "университет кино и телевидения"). For a person
    an ordinary dictionary word stops it too when more words follow ("Алиса Сама
    Пользуется"), and so does a final adjective ("Марина Добрый"), but a lone noun
    is kept ("Анна Волк"). Organisations and places are often ordinary words
    ("Северный Ключ"), so for them only verbs, function words and fillers count.
    """
    words = [(m.start() + start, m.end() + start) for m in _WORD.finditer(text[start:end])]
    for i in range(1, len(words)):
        w = text[words[i][0] : words[i][1]]
        low = w.lower()
        stop = _verbish(w) or _function_word(low) or low in _FILLER
        if stop and kind != Kind.PERSON and w.islower():
            # Inside a company or place name function words are lowercase ("кино и
            # телевидения", "Кофе и книги"); a run of speech capitalises them.
            stop = _verbish(w)
        if not stop and kind == Kind.PERSON and _plain_word(w):
            if i < len(words) - 1:
                stop = True
            else:
                parses = morph_vocab().parse(low)
                stop = bool(parses) and parses[0].tag.POS in _ADJ_POS
        if stop:
            return words[i - 1][1]
    return end


def _drop_lead_words(text: str, start: int, end: int) -> int:
    """Start of a person's name after ordinary words glued in front ("Соседка Зоя Петровна")."""
    words = [(m.start() + start, m.end() + start) for m in _WORD.finditer(text[start:end])]
    while len(words) > 1 and _plain_word(text[words[0][0] : words[0][1]]) and not all(
        _plain_word(text[a:b]) for a, b in words[1:]
    ):
        words.pop(0)
    return words[0][0] if words else start


def _finding_piece(
    text: str,
    start: int,
    end: int,
    kind: Kind,
    source: str,
    normal: str,
    lang: str,
    noisy: bool = False,
) -> Finding | None:
    s, e = fix_span(text, start, end)
    if lang == "ru" and e > s:
        s2, e2 = _trim_words(text, s, e)
        if (s2, e2) != (s, e):
            s, e = fix_span(text, s2, e2)
            normal = ""  # normal was built from the untrimmed span
    if lang == "ru" and e > s:
        e2 = _cut_tail(text, s, e, kind)
        s2 = _drop_lead_words(text, s, e2) if kind == Kind.PERSON else s
        if (s2, e2) != (s, e):
            s, e, normal = s2, e2, ""
    if e <= s:
        return None
    span = text[s:e]
    if _bad(span, kind, lang):
        return None
    a0, b0 = fix_span(text, start, end)
    words = _WORD.findall(span)
    dropped = len(_WORD.findall(text[a0:b0])) - len(words)
    if lang == "ru" and dropped >= 2 and len(words) == 1 and (_plain_word(words[0]) or span.islower()):
        return None  # what is left of a run of speech: "Группы" from "Группы Типа Команда Ну"
    if lang == "ru" and noisy and kind in (Kind.ORG, Kind.LOCATION) and words:
        # Capitals mean nothing in this part of the text: a lone ordinary word
        # ("Минут") or a run of three and more ("Реклама Скидка Совет") is speech.
        # Two ordinary words are kept: that is how companies are named ("Камский
        # Хлеб"), and a legal form or any non-dictionary word keeps a name as well.
        if len(words) != 2 and all(_plain_word(w) for w in words):
            return None
    if (s, e) != (start, end) and normal:
        normal = _balance_normal(normal)
    if normal == span:
        normal = ""
    return Finding(start=s, end=e, text=span, kind=kind, source=source, normal=normal)


# ---- layers ---------------------------------------------------------------


def _run_natasha(text: str, parts: list[tuple[int, str]]) -> Iterator[Finding]:
    segmenter, morph_tagger, ner_tagger, vocab = _natasha()
    from natasha import Doc

    for off, piece in parts:
        noisy = noisy_capitals(piece)
        doc = Doc(piece)
        doc.segment(segmenter)
        doc.tag_ner(ner_tagger)
        if not doc.spans:
            continue
        doc.tag_morph(morph_tagger)
        for sp in doc.spans:
            kind = _LABELS.get(sp.type)
            if kind is None:
                continue
            normal = ""
            try:
                sp.normalize(vocab)
                normal = sp.normal or ""
            except Exception:  # normalization is best effort
                normal = ""
            f = _finding(
                text, off + sp.start, off + sp.stop, kind, "natasha", normal, "ru", noisy
            )
            if f:
                yield f


def _spacy_normal(ent, kind: Kind, lang: str) -> str:
    if lang != "ru":
        return ""
    toks = [t for t in ent if not t.is_punct and not t.is_space]
    if not toks:
        return ""
    # Multi-word ORG / LOCATION: per-token lemmas break agreement
    # ("Красной площади" -> "красный площадь"), keep the surface.
    if kind != Kind.PERSON and len(toks) > 1:
        return ""
    if any(t.text in '«»"“”„' for t in ent):
        return ""
    out = []
    for t in ent:
        lemma = t.lemma_ or t.text
        if t.text.isupper() and len(t.text) > 1:
            lemma = t.text
        elif t.text[:1].isupper():
            lemma = lemma[:1].upper() + lemma[1:]
        out.append(lemma + t.whitespace_)
    return "".join(out).strip()


def _run_spacy(text: str, parts: list[tuple[int, str]], lang: str) -> Iterator[Finding]:
    nlp = _spacy(lang)
    docs = nlp.pipe((piece for _, piece in parts), batch_size=16)
    for (off, piece), doc in zip(parts, docs):
        noisy = noisy_capitals(piece)
        for ent in doc.ents:
            kind = _LABELS.get(ent.label_)
            if kind is None:
                continue
            normal = _spacy_normal(ent, kind, lang)
            f = _finding(
                text,
                off + ent.start_char,
                off + ent.end_char,
                kind,
                "spacy",
                normal,
                lang,
                noisy,
            )
            if f:
                yield f


def find_ner(
    text: str, langs: Iterable[str], layers: Iterable[str] = NER_LAYERS
) -> list[Finding]:
    """PERSON / ORG / LOCATION findings from natasha (ru) and spaCy (ru, en)."""
    langs = list(langs)
    layers = set(layers)
    if not text.strip():
        return []
    parts = chunks(text)
    out: list[Finding] = []
    if "natasha" in layers and "ru" in langs:
        out.extend(_run_natasha(text, parts))
    if "spacy" in layers:
        for lang in langs:
            if lang in _SPACY_MODELS:
                out.extend(_run_spacy(text, parts, lang))
    # Drop exact duplicates (spaCy ru and en can agree on a span).
    seen: set[tuple] = set()
    uniq = []
    for f in sorted(out, key=lambda f: (f.start, -f.end, f.source)):
        k = (f.start, f.end, f.kind, f.source)
        if k not in seen:
            seen.add(k)
            uniq.append(f)
    return uniq
