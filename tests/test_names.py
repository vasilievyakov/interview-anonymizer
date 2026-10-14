"""Person name identity across Russian cases, gender and initials."""

import pytest

from anon.names import name_key, same_person


@pytest.mark.parametrize(
    "form",
    ["Марией Ковалевой", "Мария Ковалева", "Марии Ковалевой", "МАРИЯ КОВАЛЕВА", "мария ковалёва"],
)
def test_full_name_forms_share_key(form):
    assert name_key(form) == name_key("Мария Ковалева") == "мария ковалев"


@pytest.mark.parametrize("form", ["Ковалевой", "Ковалева", "Ковалев", "Ковалеву", "Ковалевым"])
def test_surname_forms_share_key(form):
    assert name_key(form) == "ковалев"


@pytest.mark.parametrize("form", ["Марией", "Марии", "Мария", "марию"])
def test_first_name_forms_share_key(form):
    assert name_key(form) == "мария"


def test_other_names_in_oblique_cases():
    assert name_key("Димой Соловьевым") == name_key("Дима Соловьев")
    assert name_key("Анной Сергеевной Кузнецовой") == name_key("Анна Сергеевна Кузнецова")
    assert name_key("Бродской") == name_key("Бродский")
    assert name_key("Юлией") == name_key("Юлия")


def test_indeclinable_surnames_stay():
    assert name_key("Шевченко") == "шевченко"
    assert name_key("Черных") == "черных"


def test_english_names_are_casefolded():
    assert name_key("John SMITH") == "john smith"
    assert name_key("Mike O'Brien") == name_key("mike o'brien")


@pytest.mark.parametrize(
    "a,b",
    [
        ("Марией Ковалевой", "Мария Ковалева"),
        ("Ковалевой", "Мария Ковалева"),
        ("Ковалеву", "Мария Ковалева"),
        ("Ковалев", "Ковалевой"),
        ("Мария Ковалева", "Мария Петровна Ковалева"),
        ("Ковалева", "Ковалева Мария"),
        ("Smith", "John Smith"),
        ("Sarah Johnson", "sarah johnson"),
    ],
)
def test_same_person_true(a, b):
    assert same_person(a, b)
    assert same_person(b, a)


@pytest.mark.parametrize(
    "a,b",
    [
        ("Мария", "Мария Ковалева"),
        ("Марией", "Мария Ковалева"),
        ("Мария", "Ковалева Мария"),
        ("Мария Ковалева", "Анна Ковалева"),
        ("Мария Ковалева", "Мария Иванова"),
        ("Петровна", "Мария Петровна Ковалева"),
        ("John", "John Smith"),
        ("John Smith", "Jane Smith"),
        ("", "Мария Ковалева"),
    ],
)
def test_same_person_false(a, b):
    assert not same_person(a, b)
    assert not same_person(b, a)


@pytest.mark.parametrize("short", ["Ковалева М.", "М. Ковалева", "Ковалева М.А.", "М.А. Ковалева"])
def test_initials_match_full_name(short):
    assert same_person(short, "Мария Ковалева")
    assert same_person("Марией Ковалевой", short)


def test_initials_must_agree():
    assert not same_person("А. Ковалева", "Мария Ковалева")
    assert not same_person("Ковалева М.А.", "Мария Борисовна Ковалева")
    assert same_person("Ковалева М.Б.", "Мария Борисовна Ковалева")
    assert same_person("Ковалева М.", "М. Ковалева")
    assert not same_person("Ковалева М.", "А. Ковалева")
    assert same_person("J. Smith", "John Smith")
    assert not same_person("K. Smith", "John Smith")


def test_initials_alone_match_nothing():
    assert not same_person("М.А.", "Мария Ковалева")


@pytest.mark.parametrize(
    "surface,expected",
    [
        ("Марией Ковалевой", "Мария Ковалева"),
        ("Ковалевой", "Ковалева"),
        ("Олегом Викторовичем", "Олег Викторович"),
        ("Анной Римской-Корсаковой", "Анна Римская-Корсакова"),
        ("Санек", "Санек"),
        ("John Carter", "John Carter"),
        ("Ковалева М.А.", "Ковалева М.А."),
    ],
)
def test_nominative_keeps_gender_and_no_yo(surface, expected):
    from anon.names import nominative

    assert nominative(surface) == expected
