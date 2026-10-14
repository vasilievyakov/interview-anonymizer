from anon.model import Kind, Merged
from anon.replace import apply, apply_with_report
from anon.vault import Vault, fold


def span(text: str, sub: str, kind: Kind = Kind.PERSON, normal: str = "", nth: int = 0):
    start = -1
    for _ in range(nth + 1):
        start = text.index(sub, start + 1)
    return Merged(start, start + len(sub), sub, kind, ["natasha"], normal)


def persons(vault: Vault):
    return [e for e in vault.entities if e.kind == Kind.PERSON]


INTERVIEW = (
    "Интервьюер: Расскажите, кто у вас отвечает за закупки?\n"
    "Респондент: Этим занимается Мария Ковалева. С Марией Ковалевой мы работаем "
    "третий год, Ковалевой я доверяю. Позвоните ей: +7 916 123-45-67."
)


def test_oblique_forms_collapse_to_one_label():
    v = Vault()
    spans = [
        span(INTERVIEW, "Мария Ковалева", normal="Мария Ковалева"),
        span(INTERVIEW, "Марией Ковалевой", normal="Мария Ковалева"),
        span(INTERVIEW, "Ковалевой", normal="Ковалева", nth=1),
        span(INTERVIEW, "+7 916 123-45-67", kind=Kind.PHONE),
    ]
    spans[3].sources = ["rules"]
    out = apply(INTERVIEW, spans, v, "ru")
    assert "Ковалев" not in out
    assert out.count("[ИМЯ_1]") == 3
    assert "[ТЕЛЕФОН_1]" in out
    assert "+7" not in out
    assert len(persons(v)) == 1
    assert persons(v)[0].canonical == "Мария Ковалева"


def test_canonical_upgraded_to_longer_form():
    text = "Ковалева позвонила утром. Потом Мария Ковалева прислала отчет."
    v = Vault()
    spans = [
        span(text, "Ковалева", normal="Ковалева"),
        span(text, "Мария Ковалева", normal="Мария Ковалева"),
    ]
    out = apply(text, spans, v, "ru")
    assert out == "[ИМЯ_1] позвонила утром. Потом [ИМЯ_1] прислала отчет."
    assert len(persons(v)) == 1
    assert persons(v)[0].canonical == "Мария Ковалева"


def test_lowercase_normal_gets_title_case_canonical():
    text = "Встреча с Марией Ковалевой."
    v = Vault()
    apply(text, [span(text, "Марией Ковалевой", normal="мария ковалева")], v, "ru")
    assert persons(v)[0].canonical == "Мария Ковалева"


def test_ambiguous_namesakes_not_glued():
    text = (
        "Мария Ковалева ведет закупки, Анна Ковалева ведет продажи. "
        "Вчера Ковалевой не было на месте."
    )
    v = Vault()
    spans = [
        span(text, "Мария Ковалева", normal="Мария Ковалева"),
        span(text, "Анна Ковалева", normal="Анна Ковалева"),
        span(text, "Ковалевой", normal="Ковалева"),
    ]
    out, report = apply_with_report(text, spans, v, "ru")
    assert len(persons(v)) == 3
    assert [lab for lab, _ in report] == ["[ИМЯ_1]", "[ИМЯ_2]", "[ИМЯ_3]"]
    assert "Ковалев" not in out


def test_two_different_people_same_surname_stay_apart():
    text = "Петр Иванов и Ольга Иванова пришли вместе."
    v = Vault()
    spans = [
        span(text, "Петр Иванов", normal="Петр Иванов"),
        span(text, "Ольга Иванова", normal="Ольга Иванова"),
    ]
    out = apply(text, spans, v, "ru")
    assert out == "[ИМЯ_1] и [ИМЯ_2] пришли вместе."


def test_known_variant_catches_missed_repeat():
    text = "Мария Ковалева пришла. Потом мария ковалева ушла, а Ковалева осталась."
    v = Vault()
    # Detector saw only the first mention.
    out = apply(text, [span(text, "Мария Ковалева", normal="Мария Ковалева")], v, "ru")
    assert out.startswith("[ИМЯ_1] пришла. Потом [ИМЯ_1] ушла")
    # "Ковалева" alone is the surname of a known full name: hidden by the forms pass.
    assert out.endswith("а [ИМЯ_1] осталась.")


def test_vault_from_earlier_file_catches_repeat():
    v = Vault()
    first = "Анна Смирнова из отдела кадров."
    apply(first, [span(first, "Анна Смирнова", normal="Анна Смирнова")], v, "ru")
    second = "Сегодня АННА СМИРНОВА не пришла. Анна Смирновна тут ни при чем."
    out = apply(second, [], v, "ru")
    assert out == "Сегодня [ИМЯ_1] не пришла. Анна Смирновна тут ни при чем."


def test_literal_pass_respects_word_boundaries_and_yo():
    v = Vault()
    v.get_or_create(Kind.ORG, "Ромашка", canonical="Ромашка")
    v.get_or_create(Kind.PERSON, "Пётр Семёнов", canonical="Пётр Семёнов")
    text = "Ромашками пахнет. Ромашка платит. Петр Семенов и пётр семёнов."
    out = apply(text, [], v, "ru")
    assert out == "Ромашками пахнет. [ОРГ_1] платит. [ИМЯ_1] и [ИМЯ_1]."


def test_vault_added_strings_replaced():
    v = Vault()
    v.added.append(("Проект Звезда", Kind.ORG))
    text = "Мы работали над проектом. Проект Звезда закрыт, проект звезда в архиве."
    out, report = apply_with_report(text, [], v, "ru")
    assert out == "Мы работали над проектом. [ОРГ_1] закрыт, [ОРГ_1] в архиве."
    assert report == [("[ОРГ_1]", "Проект Звезда"), ("[ОРГ_1]", "проект звезда")]
    assert v.entities[0].canonical == "Проект Звезда"


def test_added_string_not_in_text_creates_nothing():
    v = Vault()
    v.added.append(("Проект Звезда", Kind.ORG))
    apply("Пусто.", [], v, "ru")
    assert v.entities == []


def test_short_variants_skipped_in_literal_pass():
    v = Vault()
    v.get_or_create(Kind.PERSON, "Ли", canonical="Ли")
    out = apply("Ли сказал, что ли.", [], v, "ru")
    assert out == "Ли сказал, что ли."


def test_ignored_spans_and_variants_skipped():
    text = "Москва большая. Компания Ромашка тоже."
    v = Vault()
    v.ignored.add(fold("Москва"))
    spans = [
        span(text, "Москва", kind=Kind.LOCATION),
        span(text, "Ромашка", kind=Kind.ORG),
    ]
    out = apply(text, spans, v, "ru")
    assert out == "Москва большая. Компания [ОРГ_1] тоже."
    assert all(e.kind != Kind.LOCATION for e in v.entities)


def test_english_labels():
    text = "I spoke with John Smith. Smith said John Smith's email is js@example.com."
    v = Vault()
    spans = [
        span(text, "John Smith", normal="John Smith"),
        span(text, "js@example.com", kind=Kind.EMAIL),
    ]
    out, report = apply_with_report(text, spans, v, "en")
    assert out == (
        "I spoke with [PERSON_1]. Smith said [PERSON_1]'s email is [EMAIL_1]."
    )
    assert report[0] == ("[PERSON_1]", "John Smith")
    assert report[-1] == ("[EMAIL_1]", "js@example.com")


def test_overlapping_spans_defensive():
    text = "Мария Ковалева пришла."
    v = Vault()
    spans = [
        span(text, "Ковалева", normal="Ковалева"),
        span(text, "Мария Ковалева", normal="Мария Ковалева"),
    ]
    out = apply(text, spans, v, "ru")
    assert out == "[ИМЯ_1] пришла."


def test_existing_labels_untouched():
    v = Vault()
    v.get_or_create(Kind.PERSON, "ИМЯ", canonical="ИМЯ")
    text = "[ИМЯ_1] и ИМЯ рядом."
    out = apply(text, [], v, "ru")
    assert out == "[ИМЯ_1] и [ИМЯ_1] рядом."


def test_same_person_across_files_keeps_number():
    v = Vault()
    a = "Мария Ковалева, Петр Иванов."
    apply(
        a,
        [
            span(a, "Мария Ковалева", normal="Мария Ковалева"),
            span(a, "Петр Иванов", normal="Петр Иванов"),
        ],
        v,
        "ru",
    )
    b = "Пришел Петр Иванов."
    out = apply(b, [span(b, "Петр Иванов", normal="Петр Иванов")], v, "en")
    assert out == "Пришел [PERSON_2]."


def test_forms_pass_hides_other_cases_of_a_known_name():
    text = "Работала в «Северном Ветре», про северный ветер не жалею. Потом Ковалевой звонила."
    v = Vault()
    v.get_or_create(Kind.PERSON, "Мария Ковалева", canonical="Мария Ковалева")
    out = apply(text, [span(text, "Северном Ветре", kind=Kind.ORG)], v, "ru")
    # Another case of a two-word name, even lowercase; a surname alone in another case.
    assert out == "Работала в «[ОРГ_1]», про [ОРГ_1] не жалею. Потом [ИМЯ_1] звонила."
