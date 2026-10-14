"""Vault, language detection, leak check, review grouping."""

import pytest

from anon.i18n import t
from anon.lang import detect, label_language, languages
from anon.leak import find_leaks
from anon.model import Kind, Merged
from anon.review import Collector, Item, apply_decisions, read_csv, write_csv
from anon.vault import Vault, VaultError


def test_lang():
    assert detect("Я работаю в Казани с 2019 года") == "ru"
    assert detect("I work in Leeds since 2019") == "en"
    assert detect("Мы продаем на Amazon и Shopify, через Brightline Logistics в Leeds") == "mixed"
    assert languages("Мы продаем на Amazon и Shopify, через Brightline Logistics в Leeds") == ["ru", "en"]
    assert label_language("I work in Leeds") == "en"


def test_vault_roundtrip_and_password(tmp_path):
    v = Vault()
    e = v.get_or_create(Kind.PERSON, "Марией Ковалевой", "Мария Ковалева")
    v.ignored.add("wildberries")
    v.added.append(("Санек", Kind.PERSON))
    assert v.label(e, "ru") == "[ИМЯ_1]"
    assert v.label(e, "en") == "[PERSON_1]"
    v.save(tmp_path, "secret")
    raw = (tmp_path / ".anon" / "vault.bin").read_bytes()
    assert "Ковалев".encode() not in raw and b"wildberries" not in raw
    loaded = Vault.load(tmp_path, "secret")
    assert loaded.to_json() == v.to_json()
    with pytest.raises(VaultError):
        Vault.load(tmp_path, "wrong")


def test_vault_numbering_per_kind():
    v = Vault()
    a = v.get_or_create(Kind.PERSON, "Петров")
    b = v.get_or_create(Kind.ORG, "ООО «Ромашка»")
    c = v.get_or_create(Kind.PERSON, "Сидоров")
    assert (a.key, b.key, c.key) == (1, 1, 2)
    assert v.get_or_create(Kind.PERSON, "ПЕТРОВ") is a


def test_leak_check_finds_forms_and_quotes():
    v = Vault()
    v.get_or_create(Kind.ORG, "ООО «Северный ветер»")
    v.get_or_create(Kind.PERSON, "Мария Ковалева")
    text = 'Работаю в ООО "Северный ветер".\nМария  Ковалёва сказала, что [ИМЯ_1] прав.'
    leaks = find_leaks(text, v)
    values = sorted(l.value for l in leaks)
    assert values == sorted(['ООО "Северный ветер"', "Мария  Ковалёва"])
    assert {l.line for l in leaks} == {1, 2}


def test_leak_check_word_boundary_and_ignored():
    v = Vault()
    v.get_or_create(Kind.PERSON, "Олег")
    v.ignored.add("олег")
    assert find_leaks("Олегович пришел", Vault(entities=v.entities)) == []
    assert find_leaks("Олег пришел", v) == []
    assert len(find_leaks("Олег пришел", Vault(entities=v.entities))) == 1


def test_leak_check_extra_strings():
    assert len(find_leaks("звонил Санек вчера", Vault(), extra=["Санек"])) == 1


def test_review_groups_name_forms(tmp_path):
    c = Collector()
    c.add(Kind.PERSON, "Марией Ковалевой", "a.md", ["natasha"], "ctx", "Мария Ковалева")
    c.add(Kind.PERSON, "Мария Ковалева", "b.md", ["spacy"], "ctx")
    c.add(Kind.ORG, "Wildberries", "a.md", ["spacy"], "ctx")
    items = c.items()
    person = next(i for i in items if i.kind == Kind.PERSON)
    assert person.count == 2 and person.files == {"a.md", "b.md"}
    assert person.sources == {"natasha", "spacy"}
    path = tmp_path / "review.csv"
    write_csv(items, path)
    back = read_csv(path)
    assert [(i.kind, i.text, i.count) for i in back] == [(i.kind, i.text, i.count) for i in items]


def test_review_decisions_go_to_vault(tmp_path):
    items = [
        Item(kind=Kind.ORG, text="Wildberries", keep=False, variants={"Wildberries"}),
        Item(kind=Kind.PERSON, text="Санек", keep=True, variants={"Санек"}, sources={"user"}),
        Item(kind=Kind.PERSON, text="Петров", keep=True, variants={"Петров"}, sources={"natasha"}),
    ]
    v = Vault()
    assert apply_decisions(items, v) == (2, 1, 1)
    assert v.is_ignored("WILDBERRIES")
    assert ("Санек", Kind.PERSON) in v.added


def test_review_csv_accepts_russian_marks(tmp_path):
    path = tmp_path / "review.csv"
    path.write_text("keep,kind,text\nнет,ORG,Ozon\nда,PERSON,Петров\n", encoding="utf-8")
    items = read_csv(path)
    assert [i.keep for i in items] == [False, True]


def test_messages_both_languages(monkeypatch):
    monkeypatch.setenv("ANON_LANG", "ru")
    assert t("password_prompt").startswith("Пароль")
    monkeypatch.setenv("ANON_LANG", "en")
    assert t("password_prompt").startswith("Vault")


def test_leak_check_ignores_text_inside_labels():
    v = Vault()
    v.get_or_create(Kind.PERSON, "ИМЯ_3")
    assert find_leaks("оформлен как [ИМЯ_3], но [имя_3] тоже", v) == []


def test_leak_check_skips_allowed_values():
    v = Vault()
    v.get_or_create(Kind.ORG, "СНИЛС")
    assert find_leaks("ФИО\tСНИЛС", v, skip={"снилс"}) == []


def test_leak_check_does_not_bridge_words_across_a_label():
    # "Анна Ли" must not match "Анна [ИМЯ_12] Ли": the label is not whitespace.
    v = Vault()
    v.get_or_create(Kind.PERSON, "Анна Ли")
    assert find_leaks("это Анна [ИМЯ_12] Ли сказала", v) == []


def test_leak_check_follows_the_lowercase_speech_rule():
    from anon.leak import find_leaks
    from anon.replace import apply

    v = Vault()
    text = "Работала в Лавке, а лавка у дома рядом."
    a = text.index("Лавке")
    out = apply(text, [Merged(a, a + 5, "Лавке", Kind.ORG, ["natasha"], "")], v, "ru")
    assert out.startswith("Работала в [ОРГ_1]")
    assert "лавка у дома" in out  # lowercase speech stays
    assert find_leaks(out, v) == []  # and the check does not stop the file on it
