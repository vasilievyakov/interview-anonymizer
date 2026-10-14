import pytest

from anon.model import Kind, Merged
from anon.replace import apply
from anon.restore import restore
from anon.vault import Vault


@pytest.fixture(autouse=True)
def english_messages(monkeypatch):
    # Problem reports are localized; most assertions below check the English text.
    monkeypatch.setenv("ANON_LANG", "en")


def make_vault() -> Vault:
    v = Vault()
    v.get_or_create(Kind.PERSON, "Мария Ковалева", canonical="Мария Ковалева")
    v.get_or_create(Kind.ORG, "ООО «Ромашка»", canonical="ООО «Ромашка»")
    return v


def test_round_trip_gives_canonical_names():
    text = "Респондент: С Марией Ковалевой мы работаем. Мария Ковалева в ООО «Ромашка»."
    i = text.index("Марией Ковалевой")
    j = text.index("Мария Ковалева")
    k = text.index("ООО «Ромашка»")
    spans = [
        Merged(i, i + 16, "Марией Ковалевой", Kind.PERSON, ["natasha"], "Мария Ковалева"),
        Merged(j, j + 14, "Мария Ковалева", Kind.PERSON, ["natasha"], "Мария Ковалева"),
        Merged(k, k + 13, "ООО «Ромашка»", Kind.ORG, ["natasha"]),
    ]
    v = Vault()
    anon = apply(text, spans, v, "ru")
    assert anon == "Респондент: С [ИМЯ_1] мы работаем. [ИМЯ_1] в [ОРГ_1]."
    back, problems = restore(anon, v)
    assert back == "Респондент: С Мария Ковалева мы работаем. Мария Ковалева в ООО «Ромашка»."
    assert problems == []


def test_exact_labels_both_languages_silent():
    v = make_vault()
    back, problems = restore("[ИМЯ_1] and [PERSON_1] at [ORG_1].", v)
    assert back == "Мария Ковалева and Мария Ковалева at ООО «Ромашка»."
    assert problems == []


def test_lowercase_and_mixed_case():
    v = make_vault()
    back, problems = restore("[имя_1], [Имя_1], [person_1]", v)
    assert back == "Мария Ковалева, Мария Ковалева, Мария Ковалева"
    assert len(problems) == 3
    assert all("wrong case" in p for p in problems)


def test_missing_brackets():
    v = make_vault()
    back, problems = restore("Позвонить ИМЯ_1 завтра. PERSON_1, hi.", v)
    assert back == "Позвонить Мария Ковалева завтра. Мария Ковалева, hi."
    assert len(problems) == 2
    assert "missing brackets" in problems[0]


def test_bare_label_inside_word_untouched():
    v = make_vault()
    back, problems = restore("XИМЯ_1 и ИМЯ_15", v)
    assert back == "XИМЯ_1 и ИМЯ_15"
    assert problems == ["line 1: ИМЯ_15 unknown label"]


def test_space_instead_of_underscore():
    v = make_vault()
    back, problems = restore("[ИМЯ 1] и [ ОРГ_1 ]", v)
    assert back == "Мария Ковалева и ООО «Ромашка»"
    assert "space instead of underscore" in problems[0]
    assert "extra spaces" in problems[1]


def test_bare_space_form_not_matched():
    # "место 1" is ordinary Russian; only bracketed forms may use a space.
    v = make_vault()
    v.get_or_create(Kind.LOCATION, "Тверь", canonical="Тверь")
    back, problems = restore("Мы заняли место 1 в рейтинге.", v)
    assert back == "Мы заняли место 1 в рейтинге."
    assert problems == []


def test_case_endings_dropped_and_reported():
    v = make_vault()
    text = "Поговорил с [ИМЯ_1]-ой.\nПисьмо [ИМЯ_1]ой ушло.\nОтвет ИМЯ_1ой."
    back, problems = restore(text, v)
    assert back == (
        "Поговорил с Мария Ковалева.\nПисьмо Мария Ковалева ушло.\nОтвет Мария Ковалева."
    )
    assert len(problems) == 3
    assert problems[0].startswith("line 1: [ИМЯ_1]-ой")
    assert "check grammar" in problems[0]
    assert problems[1].startswith("line 2:")
    assert problems[2].startswith("line 3:")


def test_glued_word_not_eaten():
    v = make_vault()
    back, problems = restore("[ИМЯ_1]привет", v)
    assert back == "Мария Ковалевапривет"
    assert problems == []


def test_unknown_labels_left_and_reported():
    v = make_vault()
    text = "ok\nok\nСпросить [ИМЯ_7] и [PERSON_9], [МЕСТО_1]."
    back, problems = restore(text, v)
    assert back == text
    assert problems == [
        "line 3: [ИМЯ_7] unknown label",
        "line 3: [PERSON_9] unknown label",
        "line 3: [МЕСТО_1] unknown label",
    ]


def test_unknown_tag_ignored():
    v = make_vault()
    back, problems = restore("[FOO_1] and [TODO_2]", v)
    assert back == "[FOO_1] and [TODO_2]"
    assert problems == []


def test_problems_follow_the_message_language(monkeypatch):
    monkeypatch.setenv("ANON_LANG", "ru")
    v = make_vault()
    _, problems = restore("С [ИМЯ_1]-ой и ИМЯ_1, а еще [ИМЯ_15].", v)
    assert problems == [
        "строка 1: [ИМЯ_1]-ой прочитано как [ИМЯ_1] -> Мария Ковалева"
        " (падежное окончание '-ой' отброшено, проверьте грамматику)",
        "строка 1: ИМЯ_1 прочитано как [ИМЯ_1] -> Мария Ковалева (нет скобок)",
        "строка 1: [ИМЯ_15], неизвестная метка",
    ]
