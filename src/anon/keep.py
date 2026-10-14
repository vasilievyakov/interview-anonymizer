"""Public names that stay in the text: the project's own list plus big cities.

Research interviews are about brands and services ("ПульсПлан", "Северная Корзина").
They are not personal, the model needs them, and without a list they fill most of
the review. `anon keep NAME...` writes them to `.anon/keep.txt`; scan marks every
finding that contains one of them as "keep as is" (keep = no in review.csv).

A kept name is matched in any grammatical form ("Северной Корзине") and, for longer
words, in speech-to-text distortions ("Фитбоксе" for "FitBox"). Built in are
Russian cities over a million people and countries: they are matched only as the
whole finding and only in their own forms, so "Москва-река" or a street stays
under review.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from functools import lru_cache
from pathlib import Path

from . import names
from .vault import VAULT_DIR

KEEP_FILE = "keep.txt"

# Russian cities over a million people, with everyday names.
CITIES = """
москва мск
санкт-петербург петербург питер спб ленинград
новосибирск
екатеринбург екб
казань
нижний новгород
красноярск
челябинск
самара
уфа
ростов-на-дону
омск
краснодар
воронеж
пермь
волгоград
"""

COUNTRIES = """
россия рф российская федерация
беларусь белоруссия
украина
казахстан
узбекистан
таджикистан
кыргызстан киргизия
азербайджан
армения
грузия
молдова молдавия
турция
китай
япония
индия
сша америка
канада
великобритания англия
германия
франция
италия
испания
израиль
оаэ эмираты
таиланд
вьетнам
египет
"""

# A multi-word builtin entry is written with spaces; one name per line part is a word,
# except the explicit two-word names below.
_MULTI = {"нижний новгород", "российская федерация"}

_WORD = re.compile(r"[^\W\d_]+(?:-[^\W\d_]+)*")
_CYR = re.compile("[а-яё]")

# Speech-to-text distortions are matched for words at least this long, this similar.
FUZZY_MIN_LEN = 5
FUZZY_RATIO = 0.8
FUZZY_RATIO_LONG = 0.75  # long words: "пульсплан" / "пульсплэн"

_TRANSLIT = [
    ("sch", "щ"),
    ("sh", "ш"),
    ("ch", "ч"),
    ("zh", "ж"),
    ("kh", "х"),
    ("ts", "ц"),
    ("ya", "я"),
    ("ea", "е"),
    ("yu", "ю"),
    ("ee", "и"),
    ("oo", "у"),
    ("ck", "к"),
    ("ph", "ф"),
    ("th", "т"),
    ("a", "а"),
    ("b", "б"),
    ("c", "к"),
    ("d", "д"),
    ("e", "е"),
    ("f", "ф"),
    ("g", "г"),
    ("h", "х"),
    ("i", "и"),
    ("j", "дж"),
    ("k", "к"),
    ("l", "л"),
    ("m", "м"),
    ("n", "н"),
    ("o", "о"),
    ("p", "п"),
    ("q", "к"),
    ("r", "р"),
    ("s", "с"),
    ("t", "т"),
    ("u", "у"),
    ("v", "в"),
    ("w", "в"),
    ("x", "кс"),
    ("y", "и"),
    ("z", "з"),
]


@lru_cache(maxsize=20000)
def translit(word: str) -> str:
    """Rough Latin -> Cyrillic spelling, only to compare with speech-to-text output."""
    out, i, w = [], 0, word.lower()
    while i < len(w):
        for lat, cyr in _TRANSLIT:
            if w.startswith(lat, i):
                out.append(cyr)
                i += len(lat)
                break
        else:
            out.append(w[i])
            i += 1
    return "".join(out)


@lru_cache(maxsize=50000)
def _keys(word: str) -> frozenset[str]:
    """Forms a word of a finding can be compared by: its lemmas, or its spelling."""
    low = word.lower().replace("ё", "е")
    if _CYR.search(low):
        from .replace import _lemmas

        return _lemmas(word)
    return frozenset({low, translit(low)})


def _entry_key(word: str) -> str:
    low = word.lower().replace("ё", "е")
    if _CYR.search(low):
        parses = names.morph_vocab().parse(low)
        return parses[0].normal_form.replace("ё", "е") if parses else low
    return low


@lru_cache(maxsize=20000)
def _personal(word: str) -> bool:
    """A word that reads as a first name, patronymic or likely surname: never fuzzy-matched."""
    low = word.lower()
    if not _CYR.search(low):
        return False
    for p in names.morph_vocab().parse(low):
        if "Name" in p.tag or "Patr" in p.tag or ("Surn" in p.tag and p.score >= 0.5):
            return True
    return False


def _similar(entry: str, word: str) -> bool:
    if len(entry) < FUZZY_MIN_LEN or _personal(word):
        return False
    a = translit(entry) if not _CYR.search(entry) else entry
    for b in _keys(word):
        b = translit(b) if not _CYR.search(b) else b
        need = FUZZY_RATIO_LONG if len(a) >= 8 else FUZZY_RATIO
        if abs(len(a) - len(b)) <= 3 and SequenceMatcher(None, a, b).ratio() >= need:
            return True
    return False


@dataclass
class _Entry:
    words: tuple[str, ...]
    whole: bool  # builtin places: must be the whole finding, no fuzzy matching


@dataclass
class KeepList:
    entries: list[_Entry] = field(default_factory=list)

    @classmethod
    def build(cls, values: list[str], builtin: bool = True) -> KeepList:
        kl = cls()
        for v in values:
            words = tuple(_entry_key(w) for w in _WORD.findall(v))
            if words:
                kl.entries.append(_Entry(words, whole=False))
        if builtin:
            for block in (CITIES, COUNTRIES):
                for line in block.strip().splitlines():
                    line = line.strip()
                    parts = [line] if line in _MULTI else _split_line(line)
                    for p in parts:
                        kl.entries.append(
                            _Entry(tuple(_entry_key(w) for w in p.split()), whole=True)
                        )
        return kl

    def matches(self, surface: str, whole: bool = False) -> bool:
        """True when a kept name occurs in surface (whole=True: surface is exactly that name)."""
        words = _WORD.findall(surface)
        if not words:
            return False
        for e in self.entries:
            n = len(e.words)
            if (e.whole or whole) and n != len(words):
                continue
            for i in range(len(words) - n + 1):
                seq = words[i : i + n]
                if all(
                    k in _keys(w) or (not e.whole and _similar(k, w))
                    for k, w in zip(e.words, seq)
                ):
                    return True
        return False


def _split_line(line: str) -> list[str]:
    """One builtin line: names separated by spaces, two-word names kept together."""
    out, rest = [], line
    for m in sorted(_MULTI, key=len, reverse=True):
        if m in rest:
            out.append(m)
            rest = rest.replace(m, " ")
    out.extend(rest.split())
    return out


def keep_path(project: Path) -> Path:
    return Path(project) / VAULT_DIR / KEEP_FILE


def read_values(project: Path) -> list[str]:
    path = keep_path(project)
    if not path.exists():
        return []
    return [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]


def add_values(project: Path, values: list[str]) -> list[str]:
    """Append new values to the project's keep list; returns the ones actually added."""
    have = {v.lower() for v in read_values(project)}
    new = []
    for v in (v.strip() for v in values):
        if v and v.lower() not in have:
            have.add(v.lower())
            new.append(v)
    if new:
        path = keep_path(project)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            for v in new:
                f.write(v + "\n")
    return new


def load(project: Path) -> KeepList:
    return KeepList.build(read_values(project))
