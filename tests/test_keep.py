"""Public names that stay in the text: the project list and builtin cities."""

import pytest

from anon.keep import KeepList, add_values, read_values

KL = KeepList.build(["PulsePlan", "FitBox", "Северная Корзина", "Ромашка"])


@pytest.mark.parametrize(
    "surface",
    ["PulsePlan", "PulsePlan'ом", "Пульсплане", "Фитбоксе", "Северной Корзине", "Ромашкой", "Ромашка Плюс"],
)
def test_project_names_in_any_form_and_distortion(surface):
    assert KL.matches(surface)


@pytest.mark.parametrize("surface", ["Москве", "Питере", "Нижнем Новгороде", "России", "Китае"])
def test_builtin_cities_and_countries(surface):
    assert KL.matches(surface)


@pytest.mark.parametrize(
    "surface",
    ["Мария Ковалева", "Ромашов", "Твери", "Москва-река", "Тверская улица", "Москва, Тверская 5"],
)
def test_people_small_towns_and_places_inside_cities_stay_under_review(surface):
    assert not KL.matches(surface)


def test_builtin_can_be_off():
    assert not KeepList.build([], builtin=False).matches("Москве")


def test_keep_file_roundtrip(tmp_path):
    assert add_values(tmp_path, ["PulsePlan", "pulseplan", "Ритмо"]) == ["PulsePlan", "Ритмо"]
    assert add_values(tmp_path, ["Ритмо"]) == []
    assert read_values(tmp_path) == ["PulsePlan", "Ритмо"]


@pytest.mark.models
def test_scan_marks_kept_names_and_apply_leaves_them(tmp_path, monkeypatch):
    from anon.cli import main

    monkeypatch.setenv("ANON_PASSWORD", "pw")
    src = tmp_path / "i.md"
    src.write_text(
        "Я Мария Ковалева из Твери, считаю шаги в PulsePlan. Потом переехала в Москву.\n",
        encoding="utf-8",
    )
    main(["--project", str(tmp_path), "keep", "PulsePlan"])
    main(["--project", str(tmp_path), "scan", str(src)])
    main(["--project", str(tmp_path), "apply"])
    out = (tmp_path / "i.anon.md").read_text(encoding="utf-8")
    assert "PulsePlan" in out and "Москву" in out
    assert "Ковалев" not in out and "Твер" not in out
