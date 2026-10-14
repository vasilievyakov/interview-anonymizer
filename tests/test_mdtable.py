"""Markdown pipe tables inside texts: columns named by their header."""

from anon.detect.mdtable import find_tables
from anon.model import Kind

TEXT = """Выборка:

| № | Респондент | Возраст | Где и когда | Модератор | Город |
|---|---|---|---|---|---|
| 01 | Лисицына Ольга | 37, Ж | ТЦ Звезда, 20.07 | Вера | Казань |
| 02 | Сомов Павел | 31 | Парк, 21.07 | Нина | Москва, САО |

| Тариф | Оценка |
|---|---|
| Супер Хит | 5 |
"""


def test_person_and_place_columns():
    found = {(f.kind, f.text) for f in find_tables(TEXT)}
    assert (Kind.PERSON, "Лисицына Ольга") in found
    assert (Kind.PERSON, "Нина") in found
    assert (Kind.PERSON, "Вера") in found
    assert (Kind.LOCATION, "Москва") in found  # the part before the comma
    # Columns that name nothing personal stay untouched.
    assert not any(t in ("37, Ж", "Супер Хит", "01") for _, t in found)


def test_offsets_point_at_cells():
    for f in find_tables(TEXT):
        assert TEXT[f.start : f.end] == f.text
        assert f.source == "column"


def test_no_table_without_separator_row():
    assert find_tables("| Респондент |\n| Анна |\n") == []
