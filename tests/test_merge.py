"""Merging layers into one span per place in the text."""

from anon.detect.merge import merge
from anon.model import Finding, Kind

TEXT = "Звонила Марии Ковалевой из ООО «Северный ветер», телефон +7 912 345-67-89."


def f(sub, kind, source, normal="", text=TEXT):
    start = text.index(sub)
    return Finding(start, start + len(sub), sub, kind, source, normal)


def test_single_layer_passthrough():
    out = merge([f("Марии Ковалевой", Kind.PERSON, "natasha", "Мария Ковалева")], TEXT)
    assert len(out) == 1
    m = out[0]
    assert TEXT[m.start : m.end] == m.text == "Марии Ковалевой"
    assert m.kind == Kind.PERSON
    assert m.sources == ["natasha"]
    assert m.normal == "Мария Ковалева"


def test_same_span_two_layers():
    out = merge(
        [
            f("Марии Ковалевой", Kind.PERSON, "spacy", "Мария Ковалёв"),
            f("Марии Ковалевой", Kind.PERSON, "natasha", "Мария Ковалева"),
        ],
        TEXT,
    )
    assert len(out) == 1
    assert out[0].sources == ["natasha", "spacy"]
    assert out[0].normal == "Мария Ковалева"


def test_overlap_takes_union():
    a = f("ООО «Северный ветер", Kind.ORG, "natasha")
    b = f("«Северный ветер»", Kind.ORG, "spacy")
    out = merge([a, b], TEXT)
    assert len(out) == 1
    assert out[0].text == "ООО «Северный ветер»"
    assert out[0].start == a.start and out[0].end == b.end


def test_nested_span():
    out = merge(
        [f("Ковалевой", Kind.PERSON, "spacy"), f("Марии Ковалевой", Kind.PERSON, "natasha")],
        TEXT,
    )
    assert len(out) == 1
    assert out[0].text == "Марии Ковалевой"
    assert out[0].sources == ["natasha", "spacy"]


def test_kind_priority_rules_over_ner():
    text = "Пишите на ivan.petrov@mail.ru завтра"
    out = merge(
        [
            f("ivan.petrov", Kind.PERSON, "spacy", text=text),
            f("ivan.petrov@mail.ru", Kind.EMAIL, "rules", text=text),
        ],
        text,
    )
    assert len(out) == 1
    assert out[0].kind == Kind.EMAIL
    assert out[0].text == "ivan.petrov@mail.ru"
    assert out[0].sources == ["rules", "spacy"]


def test_kind_priority_natasha_over_spacy():
    out = merge(
        [
            f("Северный ветер", Kind.LOCATION, "spacy"),
            f("ООО «Северный ветер»", Kind.ORG, "natasha"),
        ],
        TEXT,
    )
    assert out[0].kind == Kind.ORG


def test_three_layers_one_span():
    text = "Мой номер 8 (912) 345-67-89, звоните."
    sub = "8 (912) 345-67-89"
    out = merge(
        [
            f(sub, Kind.LOCATION, "spacy", text=text),
            f(sub, Kind.ORG, "natasha", text=text),
            f(sub, Kind.PHONE, "rules", text=text),
        ],
        text,
    )
    assert len(out) == 1
    assert out[0].kind == Kind.PHONE
    assert out[0].sources == ["rules", "natasha", "spacy"]


def test_normal_from_highest_priority_that_has_one():
    out = merge(
        [
            f("Марии Ковалевой", Kind.PERSON, "rules"),
            f("Марии Ковалевой", Kind.PERSON, "spacy", "Мария Ковалёв"),
        ],
        TEXT,
    )
    assert out[0].normal == "Мария Ковалёв"


def test_first_finding_wins_within_source():
    text = "Иван Петров Сидоров"
    out = merge(
        [
            Finding(5, 19, "Петров Сидоров", Kind.ORG, "natasha"),
            Finding(0, 11, "Иван Петров", Kind.PERSON, "natasha"),
        ],
        text,
    )
    assert len(out) == 1
    assert out[0].kind == Kind.PERSON
    assert out[0].text == text


def test_chain_of_overlaps_becomes_one():
    text = "abcdefghij"
    out = merge(
        [
            Finding(0, 3, "abc", Kind.ORG, "spacy"),
            Finding(2, 6, "cdef", Kind.ORG, "spacy"),
            Finding(5, 8, "fgh", Kind.ORG, "spacy"),
        ],
        text,
    )
    assert [(m.start, m.end) for m in out] == [(0, 8)]


def test_touching_spans_stay_apart_and_sorted():
    text = "Иван Петров"
    out = merge(
        [
            Finding(5, 11, "Петров", Kind.PERSON, "spacy"),
            Finding(0, 5, "Иван ", Kind.PERSON, "spacy"),
        ],
        text,
    )
    assert [(m.start, m.end) for m in out] == [(0, 5), (5, 11)]


def test_separate_spans_sorted_by_start():
    findings = [
        f("+7 912 345-67-89", Kind.PHONE, "rules"),
        f("ООО «Северный ветер»", Kind.ORG, "natasha"),
        f("Марии Ковалевой", Kind.PERSON, "spacy"),
    ]
    out = merge(findings, TEXT)
    assert [m.kind for m in out] == [Kind.PERSON, Kind.ORG, Kind.PHONE]
    for m in out:
        assert TEXT[m.start : m.end] == m.text


def test_empty():
    assert merge([], TEXT) == []
