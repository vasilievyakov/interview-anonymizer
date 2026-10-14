"""Agent-safe output: under an AI agent no command prints a value from the data."""

import io
import json
import os
import sys

import pytest

from anon import cli
from anon.agent import quiet
from anon.cli import main
from anon.model import Kind
from anon.review import REVIEW_FILE, Item, write_csv
from anon.vault import VAULT_DIR, Vault

SECRETS = ("Мария", "Ковалев", "Северный ветер", "345-67-89")
TEXT = (
    "Я Мария Ковалева, работаю в ООО «Северный ветер», телефон +7 912 345-67-89.\n\n"
    "Потом Мария Ковалева перезвонила.\n"
)


class _Tty(io.StringIO):
    def __init__(self, tty: bool) -> None:
        super().__init__()
        self._tty = tty

    def isatty(self) -> bool:
        return self._tty


@pytest.fixture
def clean_env(monkeypatch):
    for key in list(os.environ):
        if key.startswith("CODEX_") or key in (
            "CLAUDECODE",
            "ANON_AGENT",
            "ANON_SHOW_VALUES",
        ):
            monkeypatch.delenv(key)
    return monkeypatch


@pytest.fixture
def agent(monkeypatch):
    monkeypatch.setenv("CLAUDECODE", "1")
    monkeypatch.delenv("ANON_SHOW_VALUES", raising=False)
    monkeypatch.setenv("ANON_PASSWORD", "pw")
    monkeypatch.setenv("ANON_LANG", "ru")
    return monkeypatch


def assert_no_values(text: str) -> None:
    for secret in SECRETS:
        assert secret not in text, secret


# ---- quiet() ----------------------------------------------------------------


def test_quiet_on_terminal_without_agent(clean_env):
    clean_env.setattr(sys, "stdout", _Tty(True))
    assert quiet() is False


def test_quiet_without_terminal(clean_env):
    clean_env.setattr(sys, "stdout", _Tty(False))
    assert quiet() is True


@pytest.mark.parametrize(
    ("var", "value"),
    [
        ("CLAUDECODE", "1"),
        ("CODEX_SANDBOX", "seatbelt"),
        ("CODEX_THREAD_ID", "x"),
        ("ANON_AGENT", "1"),
    ],
)
def test_quiet_under_agent_even_on_terminal(clean_env, var, value):
    clean_env.setattr(sys, "stdout", _Tty(True))
    clean_env.setenv(var, value)
    assert quiet() is True


def test_anon_agent_other_value_is_not_agent(clean_env):
    clean_env.setattr(sys, "stdout", _Tty(True))
    clean_env.setenv("ANON_AGENT", "0")
    assert quiet() is False


def test_show_values_forces_loud(clean_env):
    clean_env.setattr(sys, "stdout", _Tty(False))
    clean_env.setenv("CLAUDECODE", "1")
    clean_env.setenv("ANON_SHOW_VALUES", "1")
    assert quiet() is False


# ---- commands under an agent -------------------------------------------------


def _review(tmp_path) -> None:
    write_csv(
        [
            Item(
                Kind.PERSON,
                "Мария Ковалева",
                count=2,
                variants={"Мария Ковалева"},
                sources={"natasha"},
                context="Я Мария Ковалева, работаю",
            ),
            Item(
                Kind.ORG,
                "ООО «Северный ветер»",
                count=1,
                variants={"ООО «Северный ветер»"},
                sources={"natasha"},
            ),
            Item(
                Kind.PHONE,
                "+7 912 345-67-89",
                count=1,
                variants={"+7 912 345-67-89"},
                sources={"rules"},
            ),
            Item(
                Kind.LOCATION,
                "Тверь",
                keep=False,
                count=1,
                variants={"Тверь"},
                sources={"spacy"},
            ),
        ],
        tmp_path / REVIEW_FILE,
    )


def test_list_prints_counts_only(tmp_path, agent, capsys):
    _review(tmp_path)
    main(["--project", str(tmp_path), "list"])
    out = capsys.readouterr().out
    assert_no_values(out)
    assert "Тверь" not in out
    assert "PERSON" in out and "ORG" in out and "PHONE" in out


def test_list_shows_values_when_asked(tmp_path, agent, capsys):
    agent.setenv("ANON_SHOW_VALUES", "1")
    _review(tmp_path)
    main(["--project", str(tmp_path), "list"])
    assert "Мария Ковалева" in capsys.readouterr().out


def test_review_refuses_in_terminal_under_agent(tmp_path, agent, capsys):
    _review(tmp_path)
    before = (tmp_path / REVIEW_FILE).read_text(encoding="utf-8-sig")
    with pytest.raises(SystemExit) as exc:
        main(["--project", str(tmp_path), "review"])
    assert exc.value.code not in (0, None)
    assert "--web" in str(exc.value.code)
    assert_no_values(capsys.readouterr().out + str(exc.value.code))
    assert (tmp_path / REVIEW_FILE).read_text(encoding="utf-8-sig") == before


def test_review_add_echoes_no_value(tmp_path, agent, capsys):
    _review(tmp_path)
    main(["--project", str(tmp_path), "review", "--add", "Анна Смирнова"])
    captured = capsys.readouterr()
    assert "Смирнов" not in captured.out + captured.err
    assert "Анна Смирнова" in (tmp_path / REVIEW_FILE).read_text(encoding="utf-8-sig")


def test_apply_leak_report_has_no_values(tmp_path, agent, capsys):
    src = tmp_path / "interview.md"
    src.write_text(TEXT, encoding="utf-8")
    _review(tmp_path)
    state = tmp_path / VAULT_DIR / "scan.json"
    state.parent.mkdir()
    state.write_text(json.dumps({"files": [str(src)]}), encoding="utf-8")
    # A replacer that misses everything: every kept value leaks.
    agent.setattr(
        cli, "_apply_text", lambda path, vault: (path.read_text(encoding="utf-8"), 0)
    )
    with pytest.raises(SystemExit) as exc:
        main(["--project", str(tmp_path), "apply"])
    assert exc.value.code == 2
    out = capsys.readouterr().out
    assert_no_values(out)
    assert "строки: 1, 3" in out
    assert "PERSON x2" in out and "ORG x1" in out and "PHONE x1" in out
    assert not (tmp_path / "interview.anon.md").exists()


def test_restore_problems_without_text(tmp_path, agent, capsys):
    vault = Vault()
    vault.get_or_create(Kind.PERSON, "Мария Ковалева")
    vault.get_or_create(Kind.ORG, "ООО «Северный ветер»")
    vault.save(tmp_path, "pw")
    answer = tmp_path / "answer.md"
    answer.write_text(
        "Итог.\nСвяжитесь с [имя_1]\nиз ОРГ_1 и [ИМЯ_7].\n", encoding="utf-8"
    )
    main(["--project", str(tmp_path), "restore", str(answer)])
    out = capsys.readouterr().out
    assert_no_values(out)
    assert "[имя_1]" not in out and "[ИМЯ_7]" not in out
    assert "3" in out and "2, 3" in out
    restored = (tmp_path / "answer.restored.md").read_text(encoding="utf-8")
    assert "Мария Ковалева" in restored


@pytest.mark.models
def test_scan_hides_file_names_and_values(tmp_path, agent, capsys):
    src = tmp_path / "Мария_Ковалева.md"
    src.write_text(TEXT, encoding="utf-8")
    main(["--project", str(tmp_path), "scan", str(src)])
    out = capsys.readouterr().out
    assert_no_values(out)
    assert "файле 1 из 1" in out
    assert "--web" in out


@pytest.mark.models
def test_whole_flow_under_agent(tmp_path, agent, capsys):
    src = tmp_path / "interview.md"
    src.write_text(TEXT, encoding="utf-8")
    main(["--project", str(tmp_path), "scan", str(src)])
    main(["--project", str(tmp_path), "list"])
    main(["--project", str(tmp_path), "apply"])
    answer = tmp_path / "answer.md"
    answer.write_text("Свяжитесь с [имя_1].\n", encoding="utf-8")
    main(["--project", str(tmp_path), "restore", str(answer)])
    captured = capsys.readouterr()
    assert_no_values(captured.out + captured.err)
    assert "Ковалев" not in (tmp_path / "interview.anon.md").read_text(encoding="utf-8")
