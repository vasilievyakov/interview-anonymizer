"""Identity of person names across grammatical forms.

"Марией Ковалевой", "Мария Ковалева" and "Ковалевой" should land on one label.
Each Cyrillic token is lemmatized with pymorphy2 (shipped with natasha), preferring
parses tagged as a first name, surname or patronymic; surnames then fold their
feminine ending to the masculine stem, so "Ковалевой", "Ковалева", "Ковалев" and
"Ковалеву" share one key. Latin tokens are only case-folded.

Single letters ("М." in "Ковалева М.А.") are initials: they never count as name
tokens by themselves, but they must agree with the first letters of the first
name / patronymic of the other name when both are compared.
"""

from __future__ import annotations

import re
import warnings
from dataclasses import dataclass
from functools import lru_cache

from .vault import fold

# Feminine surname endings folded to the masculine stem: Ковалева -> ковалев, Иванова -> иванов.
_FEM = [
    ("ова", "ов"),
    ("ева", "ев"),
    ("ёва", "ев"),
    ("ина", "ин"),
    ("ына", "ын"),
    ("ская", "ский"),
    ("цкая", "цкий"),
]

_CYR = re.compile(r"[а-яё]")
_TOKEN = re.compile(r"[\w-]+")

# Token roles.
FIRST = "first"
PATR = "patr"
SURN = "surn"
INITIAL = "initial"
OTHER = "other"  # unknown (Latin, or no name-like parse)

_ROLE_BY_GRAM = (("Name", FIRST), ("Surn", SURN), ("Patr", PATR))

_MORPH = None


def morph_vocab():
    """Shared natasha MorphVocab (pymorphy2), loaded once per process."""
    global _MORPH
    if _MORPH is None:
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message=".*pkg_resources.*")
            warnings.filterwarnings("ignore", category=DeprecationWarning)
            from natasha import MorphVocab

            _MORPH = MorphVocab()
    return _MORPH


def _fold_token(tok: str) -> str:
    for fem, masc in _FEM:
        if tok.endswith(fem) and len(tok) > len(fem) + 1:
            return tok[: -len(fem)] + masc
    return tok


@dataclass(frozen=True)
class _Tok:
    key: str
    role: str


@lru_cache(maxsize=20000)
def _analyze_token(tok: str) -> _Tok:
    """tok is already folded (lowercase, ё -> е)."""
    if len(tok) == 1:
        return _Tok(tok, INITIAL)
    if not _CYR.search(tok):
        return _Tok(tok, OTHER)
    best = None
    best_role = OTHER
    for p in morph_vocab().parse(tok):
        for gram, role in _ROLE_BY_GRAM:
            if gram in p.tag:
                if best is None or p.score > best.score:
                    best, best_role = p, role
                break
    if best is None:
        return _Tok(_fold_token(tok), OTHER)
    lemma = best.normal_form.replace("ё", "е")
    if best_role == SURN:
        lemma = "-".join(_fold_token(part) for part in lemma.split("-"))
    return _Tok(lemma, best_role)


def _analyze(text: str) -> list[_Tok]:
    return [_analyze_token(t) for t in _TOKEN.findall(fold(text)) if t.strip("-")]


def analyze(text: str) -> list[_Tok]:
    """Name tokens of text with their roles (FIRST, SURN, PATR, INITIAL, OTHER)."""
    return _analyze(text)


def name_key(text: str) -> str:
    """Gender- and case-insensitive key of a person name.

    "Марией Ковалевой" and "Мария Ковалева" -> "мария ковалев".
    Initials stay as single letters: "Ковалева М.А." -> "ковалев м а".
    """
    return " ".join(t.key for t in _analyze(text))


def _initials_agree(initials: list[str], other: list[_Tok], matched: set[str]) -> bool:
    """Initials of one name against the unmatched first name / patronymic of the other.

    Initials are read in order: the first one is the first name, the second one
    the patronymic. A missing counterpart is not a conflict.
    """
    rest = [t for t in other if t.role != INITIAL and t.key not in matched]
    firsts = [t for t in rest if t.role == FIRST]
    patrs = [t for t in rest if t.role == PATR]
    # Unknown roles (Latin names, unparsed tokens) stand in for a first name.
    if not firsts:
        firsts = [t for t in rest if t.role == OTHER]
    targets = [firsts[0] if firsts else None, patrs[0] if patrs else None]
    other_initials = [t.key for t in other if t.role == INITIAL]
    for i, ch in enumerate(initials):
        if i < len(other_initials) and other_initials[i] != ch:
            return False
        if i < len(targets) and targets[i] is not None and targets[i].key[0] != ch:
            return False
    return True


def same_person(a: str, b: str) -> bool:
    """True when one name is a token subset of the other ("Ковалевой" vs "Мария Ковалева").

    A lone first name never matches a longer name: "Мария" is too common to be
    glued to "Мария Ковалева" automatically. A lone surname does match.
    Initials must agree with the other name's first name (and patronymic).
    """
    ta, tb = _analyze(a), _analyze(b)
    fa = [t for t in ta if t.role != INITIAL]
    fb = [t for t in tb if t.role != INITIAL]
    if not fa or not fb:
        return False
    ka, kb = {t.key for t in fa}, {t.key for t in fb}
    if [t.key for t in ta] == [t.key for t in tb]:
        return True
    if len(fa) < len(fb) or (len(fa) == len(fb) and len(ta) <= len(tb)):
        (ts, fs, ks), (tl, fl, kl) = (ta, fa, ka), (tb, fb, kb)
    else:
        (ts, fs, ks), (tl, fl, kl) = (tb, fb, kb), (ta, fa, ka)
    if not ks <= kl:
        return False
    if len(fs) == 1 and len(fl) > 1:
        lone = fs[0]
        # The role of the lone token: its own parse, or its role inside the longer name.
        role = lone.role
        if role == OTHER:
            role = next((t.role for t in fl if t.key == lone.key), OTHER)
        if role == FIRST:
            return False
        if role == OTHER and fl[0].key == lone.key:
            return False  # positional fallback: the first token is the given name
    if len(fs) == 1 and len(fl) > 1 and fs[0].role == PATR:
        return False  # a lone patronymic identifies nobody
    matched = ks & kl
    initials_s = [t.key for t in ts if t.role == INITIAL]
    initials_l = [t.key for t in tl if t.role == INITIAL]
    if initials_s and not _initials_agree(initials_s, tl, matched):
        return False
    if initials_l and not _initials_agree(initials_l, ts, matched):
        return False
    return True


_NOMN_ROLES = ("Name", "Surn", "Patr")


@lru_cache(maxsize=20000)
def _nominative_token(tok: str) -> str:
    """One Cyrillic name token in the nominative case, keeping its own gender."""
    low = tok.lower()
    best = None
    for p in morph_vocab().parse(low):
        if not any(g in p.tag for g in _NOMN_ROLES) or p.feats.get("Number") == "Plur":
            continue  # plural readings of a name ("санька", gen. pl.) are never the person
        if p.feats.get("Case") == "Nom":
            return tok  # already nominative in one of its readings: keep as written
        if best is None or p.score > best.score:
            best = p
    if best is None:
        return tok
    form = best.inflect({"Nom"})
    word = form.word if form is not None else low
    if "ё" not in low:
        word = word.replace("ё", "е")
    return word[:1].upper() + word[1:] if tok[:1].isupper() or tok.islower() else word


def nominative(text: str) -> str:
    """How a person's name is written back on restore: "Марией Ковалевой" -> "Мария Ковалева".

    Each token is inflected on its own, so a woman's surname stays feminine
    (natasha's span normal sometimes returns the masculine "Ковалев").
    Latin names and initials are returned as written.
    """
    return re.sub(r"[А-Яа-яЁё]{2,}(?:-[А-Яа-яЁё]{2,})?", lambda m: "-".join(_nominative_token(p) for p in m.group(0).split("-")), text)


# Everyday forms of Russian first names -> the full names they can stand for.
# Keys and values are lemmas as `_analyze_token` gives them.
_DIMINUTIVES_SRC = {
    "александр александра": "саша саня санька санек шура сашка",
    "алексей": "леша алеша лешка",
    "анастасия": "настя настька",
    "анатолий": "толя толик",
    "андрей": "андрюша андрюха",
    "анна": "аня анька нюра",
    "антон": "антоша",
    "валентин валентина": "валя",
    "василий": "вася",
    "вера": "верочка",
    "виктор виктория": "витя вика",
    "владимир": "вова володя",
    "вячеслав ярослав владислав станислав": "слава",
    "галина": "галя",
    "георгий": "гоша жора",
    "дарья": "даша",
    "дмитрий": "дима митя",
    "евгений евгения": "женя",
    "екатерина": "катя",
    "елена": "лена",
    "елизавета": "лиза",
    "иван": "ваня",
    "ирина": "ира",
    "константин": "костя",
    "ксения": "ксюша",
    "людмила": "люда мила",
    "мария": "маша",
    "михаил": "миша",
    "надежда": "надя",
    "наталья наталия": "наташа",
    "николай": "коля",
    "ольга": "оля",
    "павел": "паша",
    "петр": "петя",
    "сергей": "сережа серега",
    "светлана": "света",
    "татьяна": "таня",
    "тимофей тимур": "тима тим",
    "юлия": "юля",
}
DIMINUTIVES: dict[str, frozenset[str]] = {}
for _full, _short in _DIMINUTIVES_SRC.items():
    for _d in _short.split():
        DIMINUTIVES[_d] = DIMINUTIVES.get(_d, frozenset()) | frozenset(_full.split())


def first_name_forms(key: str) -> frozenset[str]:
    """The key itself and every full name an everyday form can stand for ("маша" -> "мария")."""
    return frozenset({key}) | DIMINUTIVES.get(key, frozenset())

