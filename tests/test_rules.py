"""Tests for the rule-based detector (anon.detect.rules)."""

from __future__ import annotations

import pytest

from anon.detect.rules import find_rules, inn_valid, luhn_valid, snils_valid
from anon.model import Finding, Kind

# ---------------------------------------------------------------- helpers to build valid values


def make_snils(body: str) -> str:
    total = sum(int(d) * w for d, w in zip(body, range(9, 0, -1)))
    if total < 100:
        control = total
    elif total in (100, 101):
        control = 0
    else:
        control = total % 101
        if control == 100:
            control = 0
    return body + f"{control:02d}"


def _inn_ctrl(digits: str, weights: tuple[int, ...]) -> str:
    return str(sum(int(d) * w for d, w in zip(digits, weights)) % 11 % 10)


def make_inn10(body: str) -> str:
    return body + _inn_ctrl(body, (2, 4, 10, 3, 5, 9, 4, 6, 8))


def make_inn12(body: str) -> str:
    n11 = body + _inn_ctrl(body, (7, 2, 4, 10, 3, 5, 9, 4, 6, 8))
    return n11 + _inn_ctrl(n11, (3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8))


def make_luhn(body: str) -> str:
    for d in "0123456789":
        if luhn_valid(body + d):
            return body + d
    raise AssertionError("unreachable")


def break_last(digits: str) -> str:
    """Same number with the last digit changed: checksum no longer holds."""
    return digits[:-1] + str((int(digits[-1]) + 1) % 10)


def fmt_snils(d: str, sep1: str = "-", sep2: str = " ") -> str:
    return f"{d[:3]}{sep1}{d[3:6]}{sep1}{d[6:9]}{sep2}{d[9:]}"


SNILS = make_snils("108725237")
SNILS2 = make_snils("123456789")
INN10 = make_inn10("770708389")
INN12 = make_inn12("5001234567")
CARD16 = make_luhn("411111111111111")
CARD13 = make_luhn("422222222222")
CARD19 = make_luhn("621234567890123456")
AMEX = make_luhn("37828224631000")


def kinds(text: str, langs: list[str]) -> list[tuple[str, Kind]]:
    return [(f.text, f.kind) for f in find_rules(text, langs)]


def only(text: str, langs: list[str]) -> Finding:
    found = find_rules(text, langs)
    assert len(found) == 1, found
    return found[0]


def check_offsets(text: str, findings: list[Finding]) -> None:
    for f in findings:
        assert text[f.start : f.end] == f.text
        assert f.source == "rules"


# ---------------------------------------------------------------- checksum helpers


def test_generated_values_are_valid() -> None:
    assert SNILS == "10872523755"
    assert snils_valid(SNILS) and snils_valid(SNILS2)
    assert inn_valid(INN10) and inn_valid(INN12)
    assert INN10 == "7707083893"
    for card in (CARD16, CARD13, CARD19, AMEX):
        assert luhn_valid(card)
    assert CARD16 == "4111111111111111"


def test_snils_checksum_special_cases() -> None:
    # Find bodies whose weighted sum hits the 100/101 and >101 branches.
    seen = set()
    for n in range(1002000, 1002000 + 200000, 7):
        body = f"{n:09d}"
        total = sum(int(d) * w for d, w in zip(body, range(9, 0, -1)))
        branch = "lt100" if total < 100 else "eq" if total in (100, 101) else "gt"
        if branch in seen:
            continue
        seen.add(branch)
        good = make_snils(body)
        assert snils_valid(good)
        assert not snils_valid(break_last(good))
    assert {"lt100", "eq", "gt"} <= seen


def test_snils_low_numbers_are_not_checked() -> None:
    assert snils_valid("00100199800")
    assert snils_valid("00100199899")


# ---------------------------------------------------------------- EMAIL


@pytest.mark.parametrize("langs", [["ru"], ["en"], ["ru", "en"], []])
def test_email_runs_for_every_language(langs: list[str]) -> None:
    text = "Пишите на Maria.Kovaleva+hr@Example.COM, спасибо."
    f = only(text, langs)
    assert f.kind is Kind.EMAIL
    assert f.text == "Maria.Kovaleva+hr@Example.COM"
    assert f.normal == "maria.kovaleva+hr@example.com"
    check_offsets(text, [f])


def test_email_trailing_dot_and_cyrillic_domain() -> None:
    text = "Contact: john_doe@mail.co.uk. Also почта@пример.рф"
    found = find_rules(text, ["en"])
    assert [f.text for f in found] == ["john_doe@mail.co.uk", "почта@пример.рф"]
    check_offsets(text, found)


# ---------------------------------------------------------------- RU PHONE


@pytest.mark.parametrize(
    "phone",
    [
        "+7 912 345-67-89",
        "8 (912) 345 67 89",
        "89123456789",
        "+79123456789",
        "+7(912)345-67-89",
        "8-912-345-67-89",
        "8 912 345 6789",
        "79123456789",
        "+7 (495) 123-45-67",
        "8 (495) 123-45-67",
    ],
)
def test_ru_phone_positive(phone: str) -> None:
    text = f"Мой телефон {phone}, звоните."
    f = only(text, ["ru"])
    assert f.kind is Kind.PHONE
    assert f.text == phone
    check_offsets(text, [f])


def test_ru_phone_normal_form() -> None:
    for phone in ("+7 912 345-67-89", "8 (912) 345 67 89", "89123456789"):
        assert only(phone, ["ru"]).normal == "+79123456789"


@pytest.mark.parametrize(
    "text",
    [
        "84951234567",  # bare landline: not phone-shaped enough
        "74951234567",  # "7" without "+" and not mobile
        "891234567890",  # 12 digits: longer number
        "189123456789",  # preceded by a digit
        "+89123456789",  # wrong country prefix
    ],
)
def test_ru_phone_negative(text: str) -> None:
    assert [f for f in find_rules(text, ["ru"]) if f.kind is Kind.PHONE] == []


def test_ru_phone_not_in_en_only() -> None:
    assert find_rules("Call 89123456789", ["en"]) == []


# ---------------------------------------------------------------- SNILS


@pytest.mark.parametrize(
    "shown",
    [
        fmt_snils(SNILS),  # 108-725-237 55
        SNILS,  # 10872523755
        fmt_snils(SNILS, " ", " "),  # 108 725 237 55
        fmt_snils(SNILS, "-", "-"),
        fmt_snils(SNILS2),
    ],
)
def test_snils_positive(shown: str) -> None:
    text = f"СНИЛС {shown} в анкете"
    f = only(text, ["ru"])
    assert f.kind is Kind.SNILS
    assert f.text == shown
    assert f.normal == shown.replace(" ", "").replace("-", "")
    check_offsets(text, [f])


def test_snils_normal_example() -> None:
    assert only("108-725-237 55", ["ru"]).normal == "10872523755"


@pytest.mark.parametrize("bad", [break_last(SNILS), break_last(SNILS2)])
def test_snils_wrong_checksum_rejected(bad: str) -> None:
    for shown in (fmt_snils(bad), fmt_snils(bad, " ", " ")):
        assert find_rules(f"СНИЛС {shown}", ["ru"]) == []


def test_snils_low_number_needs_formatting() -> None:
    assert kinds("СНИЛС 001-001-998 77", ["ru"]) == [("001-001-998 77", Kind.SNILS)]
    assert [f for f in find_rules("00100199877", ["ru"]) if f.kind is Kind.SNILS] == []


def test_snils_all_zeros_rejected() -> None:
    assert find_rules("000-000-000 00", ["ru"]) == []


# ---------------------------------------------------------------- INN


def test_inn10_and_inn12_positive() -> None:
    text = f"ИНН организации {INN10}, ИНН физлица {INN12}."
    found = find_rules(text, ["ru"])
    assert [(f.text, f.kind, f.normal) for f in found] == [
        (INN10, Kind.INN, INN10),
        (INN12, Kind.INN, INN12),
    ]
    check_offsets(text, found)


def test_inn_wrong_checksum_rejected() -> None:
    assert find_rules(f"ИНН {break_last(INN10)}", ["ru"]) == []
    assert find_rules(f"ИНН {break_last(INN12)}", ["ru"]) == []
    # 12 digits where only the 11th check holds.
    half = INN12[:11] + str((int(INN12[11]) + 1) % 10)
    assert find_rules(f"ИНН {half}", ["ru"]) == []


def test_inn_only_standalone_runs() -> None:
    assert find_rules(f"1{INN10}", ["ru"]) == []
    assert find_rules(f"{INN10}5", ["ru"]) == []
    assert find_rules(f"A{INN10}", ["ru"]) == []
    # 11-digit run that contains a valid INN10 prefix.
    assert [f for f in find_rules(f"{INN10}0", ["ru"]) if f.kind is Kind.INN] == []
    # Grouped digits are not an INN.
    assert find_rules(f"{INN10[:4]} {INN10[4:]}", ["ru"]) == []


def test_inn_not_in_en_only() -> None:
    assert find_rules(f"Tax id {INN10}", ["en"]) == []


# ---------------------------------------------------------------- PASSPORT


@pytest.mark.parametrize(
    "text, shown",
    [
        ("Паспорт 45 06 123456 выдан", "45 06 123456"),
        ("паспорта: 4506 123456", "4506 123456"),
        ("данные паспорта серия 4506 № 123456", "4506 № 123456"),
        ("ПАСПОРТ РФ 4506123456", "4506123456"),
        ("в паспорте гражданина указано 45 06 123456", "45 06 123456"),
    ],
)
def test_passport_positive(text: str, shown: str) -> None:
    f = only(text, ["ru"])
    assert f.kind is Kind.PASSPORT
    assert f.text == shown
    assert f.normal == "4506123456"
    check_offsets(text, [f])


def test_passport_needs_context() -> None:
    assert find_rules("Номер 45 06 123456", ["ru"]) == []
    assert find_rules("Серия 4506 123456", ["ru"]) == []


def test_passport_context_window_is_40_chars() -> None:
    near = "паспорт" + " " * 33 + "4506 123456"
    assert kinds(near, ["ru"]) == [("4506 123456", Kind.PASSPORT)]
    far = "паспорт" + " " * 34 + "4506 123456"
    assert [f for f in find_rules(far, ["ru"]) if f.kind is Kind.PASSPORT] == []


def test_passport_wins_over_inn_on_same_span() -> None:
    value = make_inn10("450612345")  # series 4506, also a valid INN10
    assert inn_valid(value)
    f = only(f"паспорт {value}", ["ru"])
    assert f.kind is Kind.PASSPORT
    assert only(value, ["ru"]).kind is Kind.INN


# ---------------------------------------------------------------- CARD


@pytest.mark.parametrize("langs", [["ru"], ["en"], []])
@pytest.mark.parametrize(
    "shown",
    [
        CARD16,
        " ".join(CARD16[i : i + 4] for i in range(0, 16, 4)),
        "-".join(CARD16[i : i + 4] for i in range(0, 16, 4)),
        CARD13,
        CARD19,
        " ".join([CARD19[0:4], CARD19[4:8], CARD19[8:12], CARD19[12:16], CARD19[16:]]),
        f"{AMEX[:4]} {AMEX[4:10]} {AMEX[10:]}",
    ],
)
def test_card_positive(shown: str, langs: list[str]) -> None:
    text = f"Card: {shown}."
    f = only(text, langs)
    assert f.kind is Kind.CARD
    assert f.text == shown
    assert f.normal == shown.replace(" ", "").replace("-", "")
    check_offsets(text, [f])


def test_card_luhn_negative() -> None:
    bad = break_last(CARD16)
    assert find_rules(bad, ["ru", "en"]) == []
    spaced = " ".join(bad[i : i + 4] for i in range(0, 16, 4))
    assert find_rules(spaced, ["ru", "en"]) == []


def test_card_not_inside_longer_number() -> None:
    spaced = " ".join(CARD16[i : i + 4] for i in range(0, 16, 4))
    assert find_rules(f"12 {spaced}", ["ru", "en"]) == []
    assert find_rules(f"{spaced} 7", ["ru", "en"]) == []
    assert find_rules(f"3.{CARD16}", ["ru", "en"]) == []
    assert find_rules("0000000000000000", ["ru", "en"]) == []


# ---------------------------------------------------------------- US / UK PHONE


@pytest.mark.parametrize(
    "phone, normal",
    [
        ("(415) 555-0132", "+14155550132"),
        ("415-555-0132", "+14155550132"),
        ("+1 415 555 0132", "+14155550132"),
        ("+1-415-555-0132", "+14155550132"),
        ("415.555.0132", "+14155550132"),
        ("+14155550132", "+14155550132"),
        ("07700 900123", "+447700900123"),
        ("+44 7700 900123", "+447700900123"),
        ("07700900123", "+447700900123"),
        ("020 7946 0018", "+442079460018"),
        ("+44 20 7946 0018", "+442079460018"),
        ("0113 496 0000", "+441134960000"),
    ],
)
def test_en_phone_positive(phone: str, normal: str) -> None:
    text = f"Call me at {phone} tomorrow."
    f = only(text, ["en"])
    assert f.kind is Kind.PHONE
    assert f.text == phone
    assert f.normal == normal
    check_offsets(text, [f])


@pytest.mark.parametrize(
    "text",
    [
        "4155550132",  # bare 10 digits: not phone-shaped
        "415-5550132",  # one separator only
        "415-555.0132",  # mixed separators
        "02079460018",  # bare UK landline
        "115-555-0132",  # area cannot start with 1
    ],
)
def test_en_phone_negative(text: str) -> None:
    assert [f for f in find_rules(text, ["en"]) if f.kind is Kind.PHONE] == []


# ---------------------------------------------------------------- SSN


@pytest.mark.parametrize("shown", ["123-45-6789", "123 45 6789", "078-05-1120"])
def test_ssn_positive(shown: str) -> None:
    text = f"SSN {shown} on file"
    f = only(text, ["en"])
    assert f.kind is Kind.SSN
    assert f.text == shown
    assert f.normal == shown.replace("-", "").replace(" ", "")
    check_offsets(text, [f])


@pytest.mark.parametrize(
    "bad",
    [
        "000-12-3456",
        "666-12-3456",
        "900-12-3456",
        "999-12-3456",
        "123-00-4567",
        "123-45-0000",
        "123-45 6789",  # inconsistent separators
        "1234-45-6789",
    ],
)
def test_ssn_negative(bad: str) -> None:
    assert find_rules(f"SSN {bad}", ["en"]) == []


def test_ssn_not_in_ru_only() -> None:
    assert find_rules("123-45-6789", ["ru"]) == []


# ---------------------------------------------------------------- NINO


@pytest.mark.parametrize(
    "shown",
    ["AB123456C", "AB 12 34 56 C", "JG103759A", "ce123456d", "ZY 123456 B"],
)
def test_nino_positive(shown: str) -> None:
    text = f"NI number {shown}."
    f = only(text, ["en"])
    assert f.kind is Kind.NINO
    assert f.text == shown
    assert f.normal == shown.replace(" ", "").upper()
    check_offsets(text, [f])


@pytest.mark.parametrize(
    "bad",
    [
        "DA123456A",  # first letter D
        "FA123456A",
        "QA123456A",
        "VA123456A",
        "AO123456A",  # second letter O
        "AU123456A",
        "BG123456A",
        "GB123456A",
        "KN123456A",
        "NK123456A",
        "NT123456A",
        "TN123456A",
        "ZZ123456A",
        "AB123456E",  # suffix beyond D
        "AB12345C",  # five digits
        "XAB123456C",  # glued to a longer word
    ],
)
def test_nino_negative(bad: str) -> None:
    assert find_rules(f"NI {bad}", ["en"]) == []


# ---------------------------------------------------------------- decoys


DECOYS = [
    "Зарплата 200000 в месяц",
    "бюджет 120 000",
    "60 000 руб.",
    "Сумма 1 200 000 000 рублей",
    "It cost $12,500 last year",
    "Revenue 1,250,000,000 USD",
    "Встреча 12.04.2026 в 14.00",
    "Date 2026-04-12, April 12",
    "[00:02:33] Спикер 1: добрый день",
    "[01:12:45] Speaker 2: hello",
    "В 2025 году рост 15%, в 2026 году 23,5%",
    "Обработано 1048576 строк из 2097152",
    "Rows: 123456789",
    "Версия 1.12.0, сборка 20260412",
    "Range 2019-2026, ratio 3/4",
    "Итого 4 500 000,00 руб",
    "Курс 89.123456789",
    "ID заказа 1234567890123",
]


@pytest.mark.parametrize("text", DECOYS)
def test_decoys_do_not_fire(text: str) -> None:
    assert find_rules(text, ["ru", "en"]) == []


def test_money_suffix_blocks_numbers() -> None:
    assert find_rules(f"{INN10} руб.", ["ru"]) == []
    assert find_rules(f"{CARD16} ₽", ["ru"]) == []
    assert find_rules(f"${CARD16}", ["en"]) == []


# ---------------------------------------------------------------- mixed text, offsets, dedupe


def test_mixed_language_text() -> None:
    text = (
        "Интервью с Марией, тел. +7 912 345-67-89, почта maria@corp.ru.\n"
        f"СНИЛС {fmt_snils(SNILS)}, ИНН {INN12}.\n"
        "US office: (415) 555-0132, SSN 123-45-6789, NI AB 12 34 56 C.\n"
        f"Card {' '.join(CARD16[i : i + 4] for i in range(0, 16, 4))}, "
        "London 020 7946 0018. [00:02:33] budget 120 000, $12,500."
    )
    found = find_rules(text, ["ru", "en"])
    check_offsets(text, found)
    assert [f.kind for f in found] == [
        Kind.PHONE,
        Kind.EMAIL,
        Kind.SNILS,
        Kind.INN,
        Kind.PHONE,
        Kind.SSN,
        Kind.NINO,
        Kind.CARD,
        Kind.PHONE,
    ]
    assert [f.start for f in found] == sorted(f.start for f in found)

    ru_only = {f.kind for f in find_rules(text, ["ru"])}
    assert ru_only == {Kind.PHONE, Kind.EMAIL, Kind.SNILS, Kind.INN, Kind.CARD}
    en_only = {f.kind for f in find_rules(text, ["en"])}
    assert en_only == {Kind.PHONE, Kind.EMAIL, Kind.SSN, Kind.NINO, Kind.CARD}


def test_dedupe_identical_spans_across_sets() -> None:
    text = "mail a@b.com and card " + CARD16
    found = find_rules(text, ["ru", "en"])
    assert [(f.kind, f.text) for f in found] == [
        (Kind.EMAIL, "a@b.com"),
        (Kind.CARD, CARD16),
    ]


def test_no_overlapping_findings() -> None:
    text = (
        f"паспорт {make_inn10('450612345')} тел 89123456789 {SNILS} {INN10} "
        "+1 415 555 0132 +44 7700 900123"
    )
    found = find_rules(text, ["ru", "en"])
    check_offsets(text, found)
    for a, b in zip(found, found[1:]):
        assert a.end <= b.start


def test_offsets_with_repeats_and_newlines() -> None:
    text = "89123456789\n89123456789\r\nx 89123456789"
    found = find_rules(text, ["ru"])
    assert len(found) == 3
    check_offsets(text, found)
    assert [f.start for f in found] == [0, 12, 27]


def test_empty_and_plain_text() -> None:
    assert find_rules("", ["ru", "en"]) == []
    assert find_rules("Просто текст без данных. Plain text.", ["ru", "en"]) == []
