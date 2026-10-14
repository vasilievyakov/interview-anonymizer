"""NER layers (natasha, spaCy), span cleanup, chunking and find_all."""

import time

import pytest

import anon.detect as detect
from anon.detect import ALL_LAYERS, find_all
from anon.detect.ner import chunks, find_ner, fix_span
from anon.model import Finding, Kind, Merged

RU_INTERVIEW = """[00:01:12] Интервьюер: Расскажите, где вы работали до этого?

[00:01:20] Респондент: Ну короче, я три года была в ООО «Северный ветер», это в Екатеринбурге. Там директором был Иван Петрович Сидоров, ну такой, жесткий мужик. А с Марией Ковалевой мы вместе отдел запускали.

[00:02:05] Интервьюер: А почему ушли?

[00:02:10] Респондент: Да там, типа, зарплату задерживали. Потом меня позвали в АО "Ромашка", офис в Нижнем Новгороде. Я Ковалевой звонила, говорю, пойдем вместе. Она подумала и ушла в Сбербанк.

[00:03:00] Респондент: Вот. А Петров из Тинькофф мне еще писал, но я не ответила. С Димой Соловьевым мы в Казани пересекались на конференции, он из Яндекса.
"""

EN_INTERVIEW = """[00:00:05] Interviewer: So tell me about your last job.

[00:00:09] Respondent: Yeah, so, um, I was at Acme Corp in Boston for like three years. My manager was Sarah Johnson, and honestly she was great. Then I moved to Northwind Traders in Seattle. I still talk to Mike O'Brien sometimes, he's at Google now.
"""


def _texts(findings, kind=None, source=None):
    return {
        f.text
        for f in findings
        if (kind is None or f.kind == kind) and (source is None or f.source == source)
    }


def _offsets_ok(text, findings):
    for f in findings:
        assert text[f.start : f.end] == f.text, f


# ---- pure helpers (no models) ----------------------------------------------


def test_fix_span_extends_closing_guillemet():
    text = "Я работала в ООО «Северный ветер», там было хорошо."
    s = text.index("ООО")
    e = text.index("»")  # natasha stops right before the closing quote
    s2, e2 = fix_span(text, s, e)
    assert text[s2:e2] == "ООО «Северный ветер»"


def test_fix_span_extends_straight_quote():
    text = 'Позвали в АО "Ромашка", офис в центре.'
    s = text.index("АО")
    e = text.index('",')
    assert text[slice(*fix_span(text, s, e))] == 'АО "Ромашка"'


def test_fix_span_strips_punctuation_and_whitespace():
    text = "Ну, Иван Петров, привет."
    s = text.index(",")
    e = text.index("привет") - 1
    assert text[slice(*fix_span(text, s, e))] == "Иван Петров"


def test_fix_span_drops_lonely_quote():
    text = "магазин «Пятерочка» рядом"
    s = text.index("«")
    e = text.index("»")
    assert text[slice(*fix_span(text, s, e + 1))] == "«Пятерочка»"
    assert text[slice(*fix_span(text, s + 1, e + 1))] == "Пятерочка"


def test_fix_span_keeps_initial_dot():
    text = "Подписала Ковалева М.А. вчера."
    s = text.index("Ковалева")
    e = text.index(" вчера")
    assert text[slice(*fix_span(text, s, e))] == "Ковалева М.А."
    text = "Это сказал Петров."
    assert text[slice(*fix_span(text, text.index("Петров"), len(text)))] == "Петров"


def test_fix_span_english_possessive():
    text = "That was John's idea."
    s = text.index("John")
    assert text[slice(*fix_span(text, s, s + 6))] == "John"


def test_chunks_cover_text_and_keep_offsets():
    para = "Иван Петров работал в Казани. " * 40
    text = "\n\n".join([para] * 30)
    parts = chunks(text, limit=2000)
    assert len(parts) > 5
    for off, piece in parts:
        assert text[off : off + len(piece)] == piece
        assert len(piece) <= 2000
    # Every non-whitespace character is inside some chunk.
    covered = set()
    for off, piece in parts:
        covered.update(range(off, off + len(piece)))
    assert all(i in covered for i, c in enumerate(text) if not c.isspace())


def test_chunks_split_long_paragraph_without_blank_lines():
    text = "\n".join(f"[00:{i:02d}:00] Респондент: Мы с Ковалевой это обсуждали." for i in range(200))
    parts = chunks(text, limit=1000)
    assert len(parts) > 5
    for off, piece in parts:
        assert text[off : off + len(piece)] == piece
        assert not piece.startswith("Ковалевой")  # cut at line breaks, not mid-line


def test_find_all_rules_only_with_stub(monkeypatch):
    text = "Если что, пишите мне на рабочую почту, она очень простая: iv@ya.ru"
    s = text.index("iv@")
    calls = []

    def fake_rules(t, langs):
        calls.append(langs)
        return [Finding(s, len(text), text[s:], Kind.EMAIL, "rules")]

    monkeypatch.setattr(detect, "_find_rules", fake_rules)
    out = find_all(text, layers=("rules",))
    assert calls == [["ru"]]
    assert out == [Merged(s, len(text), "iv@ya.ru", Kind.EMAIL, ["rules"], "")]


def test_all_layers_constant():
    assert ALL_LAYERS == ("rules", "natasha", "spacy")


# ---- models ------------------------------------------------------------------


@pytest.mark.models
def test_ru_interview_entities():
    found = find_ner(RU_INTERVIEW, ["ru"])
    _offsets_ok(RU_INTERVIEW, found)
    nat = [f for f in found if f.source == "natasha"]
    persons = _texts(nat, Kind.PERSON)
    assert {"Иван Петрович Сидоров", "Марией Ковалевой", "Ковалевой", "Петров", "Димой Соловьевым"} <= persons
    assert {"ООО «Северный ветер»", 'АО "Ромашка"', "Сбербанк"} <= _texts(nat, Kind.ORG)
    assert {"Екатеринбурге", "Нижнем Новгороде", "Казани"} <= _texts(nat, Kind.LOCATION)
    # spaCy layer contributes too.
    assert "Иван Петрович Сидоров" in _texts(found, Kind.PERSON, "spacy")


@pytest.mark.models
def test_ru_normal_forms():
    found = find_ner(RU_INTERVIEW, ["ru"], layers=("natasha",))
    by_text = {f.text: f for f in found}
    assert by_text["Марией Ковалевой"].normal == "Мария Ковалева"
    assert by_text["Нижнем Новгороде"].normal == "Нижний Новгород"
    assert by_text["Екатеринбурге"].normal == "Екатеринбург"
    assert by_text["Димой Соловьевым"].key_text == "Дима Соловьев"
    assert by_text["ООО «Северный ветер»"].key_text == "ООО «Северный ветер»"


@pytest.mark.models
def test_ru_filler_and_speaker_labels_are_not_entities():
    found = find_ner(RU_INTERVIEW, ["ru"])
    texts = {f.text.lower() for f in found}
    for junk in ("интервьюер", "респондент", "расскажите", "ну", "короче", "типа", "вот", "мне"):
        assert junk not in texts
    assert not any(t.endswith(" мне") for t in texts)


@pytest.mark.models
def test_ru_conversational_snippets():
    text = (
        "Слушай, а Ковалева вообще в курсе? Я ей говорю: Маша, ну ты чего.\n\n"
        "Да, Олег Викторович сказал, что Анна Сергеевна Кузнецова уйдет в декабре.\n\n"
        "Я из Самары, но живу в Химках. Летали в Санкт-Петербург, потом под Тверью жили.\n\n"
        "Мы работали с ПАО «Газпром нефть» и с ООО «Альфа-Строй»."
    )
    found = find_ner(text, ["ru"])
    _offsets_ok(text, found)
    persons = _texts(found, Kind.PERSON)
    assert {"Ковалева", "Маша", "Олег Викторович", "Анна Сергеевна Кузнецова"} <= persons
    assert {"Самары", "Химках", "Санкт-Петербург", "Тверью"} <= _texts(found, Kind.LOCATION)
    assert {"ПАО «Газпром нефть»", "ООО «Альфа-Строй»"} <= _texts(found, Kind.ORG)


@pytest.mark.models
def test_en_interview_entities():
    found = find_ner(EN_INTERVIEW, ["en"])
    _offsets_ok(EN_INTERVIEW, found)
    assert {f.source for f in found} == {"spacy"}  # natasha is ru only
    assert {"Sarah Johnson", "Mike O'Brien"} <= _texts(found, Kind.PERSON)
    assert {"Acme Corp", "Northwind Traders", "Google"} <= _texts(found, Kind.ORG)
    assert {"Boston", "Seattle"} <= _texts(found, Kind.LOCATION)
    texts = {f.text.lower() for f in found}
    assert not texts & {"interviewer", "respondent", "yeah", "um", "three years"}


@pytest.mark.models
def test_en_lowercase_person_dropped():
    found = find_ner("yeah so i talked to john yesterday, he was fine", ["en"])
    assert not [f for f in found if f.kind == Kind.PERSON and f.text.islower()]


@pytest.mark.models
def test_natasha_skipped_for_english_only():
    found = find_ner(EN_INTERVIEW, ["en"], layers=("natasha",))
    assert found == []


@pytest.mark.models
def test_offsets_across_chunks():
    text = ("\n\n".join([RU_INTERVIEW] * 20)).strip()
    found = find_ner(text, ["ru"])
    _offsets_ok(text, found)
    sid = [f for f in found if f.text == "Иван Петрович Сидоров" and f.source == "natasha"]
    assert len(sid) == 20


@pytest.mark.models
def test_mixed_text_runs_both_spacy_models():
    text = "Мы продаем через Brightline Logistics, а с Марией Ковалевой обсуждали Amazon."
    found = find_ner(text, ["ru", "en"])
    _offsets_ok(text, found)
    assert "Марией Ковалевой" in _texts(found, Kind.PERSON, "natasha")


@pytest.mark.models
def test_find_all_merges_layers(monkeypatch):
    monkeypatch.setattr(detect, "_find_rules", lambda t, langs: [])
    out = find_all(RU_INTERVIEW)
    for m in out:
        assert RU_INTERVIEW[m.start : m.end] == m.text
    starts = [m.start for m in out]
    assert starts == sorted(starts)
    for a, b in zip(out, out[1:]):
        assert a.end <= b.start
    kov = next(m for m in out if m.text == "Марией Ковалевой")
    assert kov.kind == Kind.PERSON
    assert kov.sources == ["natasha", "spacy"]
    assert kov.normal == "Мария Ковалева"
    org = next(m for m in out if m.text == "ООО «Северный ветер»")
    assert org.kind == Kind.ORG


@pytest.mark.models
def test_find_all_with_real_rules():
    pytest.importorskip("anon.detect.rules")
    text = "Звоните Ивану Петрову: +7 912 345-67-89, почта ivan.petrov@mail.ru."
    out = find_all(text)
    kinds = {m.kind for m in out}
    assert Kind.PERSON in kinds
    assert Kind.EMAIL in kinds


@pytest.mark.models
def test_speed_50kb():
    text = ("\n\n".join([RU_INTERVIEW] * 60))[:50_000]
    find_ner("Иван Петров", ["ru"])  # warm up models
    t0 = time.perf_counter()
    found = find_ner(text, ["ru"])
    elapsed = time.perf_counter() - t0
    assert found
    assert elapsed < 10, elapsed


# ---- transcripts: speaker headers and speech-to-text capitals ---------------

STT_TRANSCRIPT = """0:01:05 - Олег (Speaker A): Меня слышно?

0:01:09 - Speaker B: Да, хорошо. Расскажите о себе.

0:02:40 - Олег (Speaker A): Мне 41. Работал продавцом, начальник был Игорь Савельев.

Ну Мясо сочное Соус нормальный, да Сыр Тоже ничего Вот Салат, его много
"""


@pytest.mark.models
def test_speaker_header_does_not_glue_to_name():
    found = find_all(STT_TRANSCRIPT, ["ru"])
    persons = {m.text for m in found if m.kind == Kind.PERSON}
    assert "Олег" in persons
    assert not any("Speaker" in p or "(" in p for p in persons)


@pytest.mark.models
def test_capitalised_ordinary_words_are_not_names():
    found = find_all(STT_TRANSCRIPT, ["ru"])
    texts = {m.text for m in found}
    for word in ("Мясо", "Сыр", "Салат", "Вот Салат", "Да"):
        assert word not in texts
    assert any("Савельев" in t for t in texts)


def test_plain_word_and_verbish():
    from anon.detect.ner import _plain_word, _verbish

    assert _plain_word("Мясо") and _plain_word("Сводка")
    assert not _plain_word("Ира") and not _plain_word("Гульнара") and not _plain_word("Телзет")
    assert _verbish("Звонила") and not _verbish("Ковалевой")


def test_generic_abbreviations_are_not_organisations():
    from anon.detect.ner import _bad

    for s in ("HR", "HR-ом", "ИП", "ООО", "СНИЛС", "IT", "МФЦ"):
        assert _bad(s, Kind.ORG, "ru")
    assert not _bad("ИП Гусев", Kind.ORG, "ru")
    assert not _bad("Сбер", Kind.ORG, "ru")


@pytest.mark.models
def test_person_span_stops_where_speech_begins():
    text = "Ну Да Зоя Петровна Говорит Что У Ритмо Скидка Была А Алиса Сама Пользуется Пульспланом\n"
    persons = {m.text for m in find_all(text, ["ru"]) if m.kind == Kind.PERSON}
    assert not any("Говорит" in p or "Пользуется" in p for p in persons)


def test_noisy_capitals_tells_speech_to_text_from_edited_text():
    from anon.detect.ner import noisy_capitals

    stt = " ".join(
        ["Да Мясо сочное Соус нормальный Сыр Тоже ничего Вот Салат его много Хлеб мягкий"] * 6
    )
    edited = (
        "Ольга Сергеевна работала в ООО «Северный ветер» вместе с Иваном Петровым, "
        "потом Мария Ковалева позвала ее в Казань, а Петр Смирнов остался в Твери. "
    ) * 4
    assert noisy_capitals(stt)
    assert not noisy_capitals(edited)


@pytest.mark.models
def test_capitalised_function_words_and_lead_words_are_trimmed():
    text = "Ну И Айдару Понравилось Про Лавку Я Не Знаю Соседка Зоя Петровна Говорит\n"
    persons = {m.text for m in find_all(text, ["ru"]) if m.kind == Kind.PERSON}
    assert not any(p.startswith(("И ", "Про ", "Соседка ")) for p in persons)


@pytest.mark.models
def test_lowercase_function_words_stay_inside_organisation_names():
    text = "Я училась в Санкт-Петербургском университете кино и телевидения, потом работала.\n"
    orgs = {m.text for m in find_all(text, ["ru"]) if m.kind == Kind.ORG}
    assert any(o.endswith("телевидения") for o in orgs), orgs
