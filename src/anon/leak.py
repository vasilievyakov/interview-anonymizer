"""Leak check: the output must not contain any real value the vault knows.

Runs after replacement. If anything is found, the file is not released.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .replace import _ordinary_lowercase
from .vault import Vault, fold

# Values shorter than this are too likely to collide with ordinary words.
MIN_LEN = 3


@dataclass(frozen=True)
class Leak:
    value: str
    line: int
    context: str


def _pattern(value: str) -> re.Pattern[str]:
    # Word boundaries on both sides; whitespace inside the value may vary.
    body = r"\s+".join(re.escape(part) for part in value.split())
    return re.compile(rf"(?<![\w]){body}(?![\w])", re.IGNORECASE)


_QUOTES = str.maketrans({c: '"' for c in "«»“”„'"})


def _fold_same_length(s: str) -> str:
    """fold() without whitespace collapsing, so offsets stay aligned with the original."""
    return s.lower().replace("ё", "е").translate(_QUOTES)


_LABEL = re.compile(r"\[[A-ZА-ЯЁ]+_\d+\]", re.IGNORECASE)


def _mask_labels(s: str) -> str:
    """Blank out labels already placed, so "[ИМЯ_3]" never counts as a leak of "ИМЯ_3"."""
    return _LABEL.sub(lambda m: "\u2588" * len(m.group(0)), s)


def find_leaks(
    text: str, vault: Vault, extra: list[str] | None = None, skip: set[str] | None = None
) -> list[Leak]:
    """Every vault value (and every extra string) still present in text.

    skip: folded values that are allowed to stay (table headers are column names, not data).
    """
    haystack = _mask_labels(_fold_same_length(text))
    values = {fold(v) for v in vault.secrets()} | {fold(v) for v in (extra or [])}
    leaks: list[Leak] = []
    for value in sorted(values, key=len, reverse=True):
        if len(value) < MIN_LEN or vault.is_ignored(value) or (skip and value in skip):
            continue
        for m in _pattern(value).finditer(haystack):
            if _ordinary_lowercase(text[m.start() : m.end()]):
                # Replacement leaves a lowercase dictionary word as speech ("лавка у
                # дома" is not the company "Лавка"); the check follows the same rule.
                continue
            line = haystack.count("\n", 0, m.start()) + 1
            a, b = max(0, m.start() - 30), min(len(text), m.end() + 30)
            leaks.append(
                Leak(
                    value=text[m.start() : m.end()],
                    line=line,
                    context=text[a:b].replace("\n", " "),
                )
            )
    leaks.sort(key=lambda x: x.line)
    return leaks
