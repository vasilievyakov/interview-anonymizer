"""Rule-based detectors for structured identifiers (phones, emails, national ids, cards).

Every detector is a regex that proposes candidates plus a validator that checks
checksums and shape. Boundaries are strict: a candidate must not touch a letter
or digit on either side, and must not continue a longer number through a single
separator ("12 4111 1111 ..." or "1.89123456789"), so substrings of longer
numbers, amounts, dates and timestamps do not match.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator

from anon.model import Finding, Kind

SOURCE = "rules"

# Left: no word char or "+" right before, and not "digit + separator" before.
_L = r"(?<![\w+])(?<!\d[ .,\-/])"
# Right: no word char right after, and not "separator + digit" after.
_R = r"(?!\w)(?![ .,\-/]\d)"

# Separators allowed inside grouped numbers (space, no-break space, dash).
_S = r"[  \-]"

_MONEY_AFTER = re.compile(
    r"\s?(?:руб|р\.|₽|\$|€|£|usd|rub|eur|gbp|долл|евро|тыс|млн|млрд|k\b|m\b|%)",
    re.IGNORECASE,
)
_MONEY_BEFORE = re.compile(r"[$€₽£]\s?$")

_PASSPORT_CONTEXT = re.compile(r"паспорт", re.IGNORECASE)
_PASSPORT_WINDOW = 40


def _digits(s: str) -> str:
    return "".join(ch for ch in s if ch.isdigit())


def _looks_like_money(text: str, start: int, end: int) -> bool:
    if _MONEY_AFTER.match(text, end):
        return True
    return bool(_MONEY_BEFORE.search(text[max(0, start - 2) : start]))


def _trivial(digits: str) -> bool:
    """All one digit (0000000000, 1111111111) - never a real identifier."""
    return len(set(digits)) <= 1


# ---------------------------------------------------------------- checksums


def snils_valid(digits: str) -> bool:
    """Official SNILS checksum. Numbers up to 001-001-998 are not checked."""
    if len(digits) != 11 or not digits.isdigit():
        return False
    body, control = digits[:9], int(digits[9:])
    if int(body) <= 1001998:
        return True
    total = sum(int(d) * w for d, w in zip(body, range(9, 0, -1)))
    if total < 100:
        expected = total
    elif total in (100, 101):
        expected = 0
    else:
        expected = total % 101
        if expected == 100:
            expected = 0
    return control == expected


_INN10_W = (2, 4, 10, 3, 5, 9, 4, 6, 8)
_INN11_W = (7, 2, 4, 10, 3, 5, 9, 4, 6, 8)
_INN12_W = (3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8)


def _inn_control(digits: str, weights: tuple[int, ...]) -> int:
    return sum(int(d) * w for d, w in zip(digits, weights)) % 11 % 10


def inn_valid(digits: str) -> bool:
    """Official INN checksum for 10-digit (legal entity) and 12-digit (person) numbers."""
    if not digits.isdigit():
        return False
    if len(digits) == 10:
        return _inn_control(digits[:9], _INN10_W) == int(digits[9])
    if len(digits) == 12:
        return _inn_control(digits[:10], _INN11_W) == int(digits[10]) and _inn_control(
            digits[:11], _INN12_W
        ) == int(digits[11])
    return False


def luhn_valid(digits: str) -> bool:
    if not digits.isdigit() or len(digits) < 2:
        return False
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


# ---------------------------------------------------------------- patterns

_EMAIL = re.compile(
    r"(?<![\w.%+\-])[\w.%+\-]+@[\w\-]+(?:\.[\w\-]+)*\.[^\W\d_]{2,}(?![\w\-])"
)

_CARD = re.compile(
    _L
    + r"(?:\d{4}(?:"
    + _S
    + r"\d{4}){2,3}(?:"
    + _S
    + r"\d{1,3})?|\d{4}"
    + _S
    + r"\d{6}"
    + _S
    + r"\d{4,5}|\d{13,19})"
    + _R
)

_RU_PHONE = re.compile(
    _L
    + r"(?P<p>\+7|8|7)(?P<s0>"
    + _S
    + r"?)(?:\((?P<a1>[34789]\d{2})\)|(?P<a2>[34789]\d{2}))"
    + r"(?P<s1>"
    + _S
    + r"?)(?P<b>\d{3})(?P<s2>"
    + _S
    + r"?)(?P<c>\d{2})(?P<s3>"
    + _S
    + r"?)(?P<d>\d{2})"
    + _R
)

_SNILS = re.compile(
    _L + r"\d{3}(?P<s1>[ \-]?)\d{3}(?P=s1)\d{3}(?P<s2>[ \-]?)\d{2}" + _R
)

_INN = re.compile(_L + r"(?:\d{12}|\d{10})" + _R)

_PASSPORT = re.compile(
    _L + r"(?P<series>\d{2} ?\d{2})(?: *(?:№|N|номер|no\.?)? *)(?P<number>\d{6})" + _R,
    re.IGNORECASE,
)

_US_PHONE = re.compile(
    _L
    + r"(?P<cc>\+1[ .\-]?)?"
    + r"(?:\((?P<a1>[2-9]\d{2})\) ?|(?P<a2>[2-9]\d{2})(?P<s1>[ .\-]?))"
    + r"(?P<ex>[2-9]\d{2})(?P<s2>[ .\-]?)(?P<ln>\d{4})"
    + _R
)

_UK_PHONE = re.compile(
    _L
    + r"(?P<pre>\+44 ?|0)"
    + r"(?P<rest>7\d{3} ?\d{6}"  # mobile: 07700 900123
    + r"|2\d ?\d{4} ?\d{4}"  # 2-digit area: 020 7946 0018
    + r"|1\d{3} ?\d{6}"  # 4-digit area: 0161 4960000 style 01632 960001
    + r"|1\d{2} ?\d{3} ?\d{4}"  # 3-digit area: 0113 496 0000
    + r"|[38]\d{2} ?\d{3} ?\d{4})"  # non-geographic: 0300, 0800
    + _R
)

_SSN = re.compile(_L + r"(?P<a>\d{3})(?P<s>[ \-])(?P<g>\d{2})(?P=s)(?P<n>\d{4})" + _R)

_NINO_BAD_PREFIX = {"BG", "GB", "KN", "NK", "NT", "TN", "ZZ"}
_NINO = re.compile(
    r"(?<![\w])(?P<p>[A-CEGHJ-PR-TW-Z][A-CEGHJ-NPR-TW-Z]) ?\d{2} ?\d{2} ?\d{2} ?[A-D](?!\w)",
    re.IGNORECASE,
)


# ---------------------------------------------------------------- detectors

Candidate = tuple[int, int, Kind, str]


def _emails(text: str) -> Iterator[Candidate]:
    for m in _EMAIL.finditer(text):
        s = m.group(0)
        # Trim a trailing dot ("write to a@b.ru.") left by the domain pattern.
        while s.endswith("."):
            s = s[:-1]
        if s.startswith(".") or ".." in s:
            continue
        yield m.start(), m.start() + len(s), Kind.EMAIL, s.lower()


def _cards(text: str) -> Iterator[Candidate]:
    for m in _CARD.finditer(text):
        digits = _digits(m.group(0))
        if not 13 <= len(digits) <= 19 or digits[0] == "0" or _trivial(digits):
            continue
        if not luhn_valid(digits) or _looks_like_money(text, m.start(), m.end()):
            continue
        yield m.start(), m.end(), Kind.CARD, digits


def _ru_phones(text: str) -> Iterator[Candidate]:
    for m in _RU_PHONE.finditer(text):
        prefix = m.group("p")
        area = m.group("a1") or m.group("a2")
        formatted = bool(
            m.group("a1")
            or m.group("s0")
            or m.group("s1")
            or m.group("s2")
            or m.group("s3")
        )
        if prefix != "+7":
            # Without "+": a bare digit run is a phone only for mobile 9xx;
            # a leading "7" without "+" is accepted only for mobile 9xx.
            if prefix == "7" and area[0] != "9":
                continue
            if not formatted and area[0] != "9":
                continue
        if _looks_like_money(text, m.start(), m.end()):
            continue
        rest = area + m.group("b") + m.group("c") + m.group("d")
        yield m.start(), m.end(), Kind.PHONE, "+7" + rest


def _snils(text: str) -> Iterator[Candidate]:
    for m in _SNILS.finditer(text):
        digits = _digits(m.group(0))
        if _trivial(digits[:9]) or not snils_valid(digits):
            continue
        formatted = bool(m.group("s1") or m.group("s2"))
        # Low numbers skip the checksum; accept them only in a SNILS-shaped layout.
        if int(digits[:9]) <= 1001998 and not formatted:
            continue
        if _looks_like_money(text, m.start(), m.end()):
            continue
        yield m.start(), m.end(), Kind.SNILS, digits


def _inns(text: str) -> Iterator[Candidate]:
    for m in _INN.finditer(text):
        digits = m.group(0)
        if digits.startswith("00") or _trivial(digits) or "000000" in digits:
            continue
        if not inn_valid(digits) or _looks_like_money(text, m.start(), m.end()):
            continue
        yield m.start(), m.end(), Kind.INN, digits


def _passports(text: str) -> Iterator[Candidate]:
    for m in _PASSPORT.finditer(text):
        window = text[max(0, m.start() - _PASSPORT_WINDOW) : m.start()]
        if not _PASSPORT_CONTEXT.search(window):
            continue
        digits = _digits(m.group("series")) + m.group("number")
        if _trivial(digits) or _looks_like_money(text, m.start(), m.end()):
            continue
        yield m.start(), m.end(), Kind.PASSPORT, digits


def _us_phones(text: str) -> Iterator[Candidate]:
    for m in _US_PHONE.finditer(text):
        s1, s2 = m.group("s1") or "", m.group("s2")
        paren = m.group("a1") is not None
        cc = m.group("cc") is not None
        if not paren and not cc:
            # "415-555-0132" / "415.555.0132" / "415 555 0132": both separators, same kind.
            if not s1 or not s2 or s1 != s2:
                continue
        if _looks_like_money(text, m.start(), m.end()):
            continue
        area = m.group("a1") or m.group("a2")
        yield (
            m.start(),
            m.end(),
            Kind.PHONE,
            "+1" + area + m.group("ex") + m.group("ln"),
        )


def _uk_phones(text: str) -> Iterator[Candidate]:
    for m in _UK_PHONE.finditer(text):
        pre, rest = m.group("pre"), m.group("rest")
        international = pre.startswith("+")
        spaced = " " in rest
        # Bare national numbers are accepted only for mobiles (07...).
        if not international and not spaced and rest[0] != "7":
            continue
        if _looks_like_money(text, m.start(), m.end()):
            continue
        yield m.start(), m.end(), Kind.PHONE, "+44" + _digits(rest)


def _ssns(text: str) -> Iterator[Candidate]:
    for m in _SSN.finditer(text):
        area, group, serial = m.group("a"), m.group("g"), m.group("n")
        if area == "000" or area == "666" or area[0] == "9":
            continue
        if group == "00" or serial == "0000":
            continue
        yield m.start(), m.end(), Kind.SSN, area + group + serial


def _ninos(text: str) -> Iterator[Candidate]:
    for m in _NINO.finditer(text):
        if m.group("p").upper() in _NINO_BAD_PREFIX:
            continue
        normal = re.sub(r"\s", "", m.group(0)).upper()
        yield m.start(), m.end(), Kind.NINO, normal


_COMMON: tuple[Callable[[str], Iterator[Candidate]], ...] = (_emails, _cards)
_RU: tuple[Callable[[str], Iterator[Candidate]], ...] = (
    _snils,
    _passports,
    _inns,
    _ru_phones,
)
_EN: tuple[Callable[[str], Iterator[Candidate]], ...] = (
    _ssns,
    _ninos,
    _us_phones,
    _uk_phones,
)

# Lower number wins when two candidates cover overlapping text with equal length.
_PRIORITY = {
    Kind.EMAIL: 0,
    Kind.CARD: 1,
    Kind.SNILS: 2,
    Kind.PASSPORT: 3,
    Kind.INN: 4,
    Kind.SSN: 5,
    Kind.NINO: 6,
    Kind.PHONE: 7,
}


def find_rules(text: str, langs: list[str]) -> list[Finding]:
    """Find structured identifiers in text.

    langs selects detector sets: "ru" and/or "en". EMAIL and CARD always run.
    Overlapping candidates are resolved to one finding: the longer span wins,
    then the kind with a stronger check (checksum before shape).
    """
    detectors = list(_COMMON)
    if "ru" in langs:
        detectors.extend(_RU)
    if "en" in langs:
        detectors.extend(_EN)

    candidates: set[Candidate] = set()
    for detector in detectors:
        candidates.update(detector(text))

    ordered = sorted(candidates, key=lambda c: (-(c[1] - c[0]), _PRIORITY[c[2]], c[0]))
    kept: list[Candidate] = []
    for cand in ordered:
        if any(cand[0] < k[1] and k[0] < cand[1] for k in kept):
            continue
        kept.append(cand)

    kept.sort(key=lambda c: c[0])
    return [
        Finding(start=s, end=e, text=text[s:e], kind=kind, source=SOURCE, normal=normal)
        for s, e, kind, normal in kept
    ]
