"""Markdown pipe tables inside texts.

NER misses names in table cells ("| 02 | Сомов Павел | 31, М |"): there is
no sentence around them. A column whose header names a person, a city or a
phone ("Респондент", "Модератор", "Город") is read the way spreadsheet columns
are: every cell under it is a finding.
"""

from __future__ import annotations

import re

from ..model import Finding, Kind

_ROW = re.compile(r"^[ \t]*\|(.*)\|[ \t]*$", re.MULTILINE)
_SEPARATOR = re.compile(r"^[\s|:\-]+$")
_NUMBERISH = re.compile(r"^[\d\s.,:;%~№#/+\-–—()]*$")


def _cells(line: str, offset: int) -> list[tuple[int, int]]:
    """(start, end) of each cell's trimmed text; offsets into the whole text."""
    out = []
    pos = 0
    for part in line.split("|"):
        a, b = pos, pos + len(part)
        while a < b and line[a].isspace():
            a += 1
        while b > a and line[b - 1].isspace():
            b -= 1
        out.append((offset + a, offset + b))
        pos += len(part) + 1
    return out


def find_tables(text: str) -> list[Finding]:
    from ..table import classify_header

    findings: list[Finding] = []
    rows = list(_ROW.finditer(text))
    i = 0
    while i + 1 < len(rows):
        head, sep = rows[i], rows[i + 1]
        adjacent = text.count("\n", head.end(), sep.start()) == 1
        if not (adjacent and _SEPARATOR.match(sep.group(1))):
            i += 1
            continue
        headers = [text[a:b] for a, b in _cells(head.group(1), head.start(1))]
        kinds = [classify_header(h)[0] for h in headers]
        j = i + 2
        prev_end = sep.end()
        while j < len(rows) and text.count("\n", prev_end, rows[j].start()) == 1:
            row = rows[j]
            for col, (a, b) in enumerate(_cells(row.group(1), row.start(1))):
                kind = kinds[col] if col < len(kinds) else None
                if kind is None or b <= a:
                    continue
                cell = text[a:b]
                if _NUMBERISH.match(cell) or not any(c.isalpha() for c in cell):
                    continue
                if kind in (Kind.PERSON, Kind.LOCATION):
                    # "ТЦ Звезда, 20.07 13:00": the name is the part before a comma.
                    cut = re.search(r"[,;(]", cell)
                    if cut:
                        b = a + cut.start()
                        while b > a and text[b - 1].isspace():
                            b -= 1
                        cell = text[a:b]
                    if not cell:
                        continue
                findings.append(
                    Finding(start=a, end=b, text=cell, kind=kind, source="column", normal="")
                )
            prev_end = row.end()
            j += 1
        i = j
    return findings
