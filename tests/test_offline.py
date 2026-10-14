"""The whole local path works with the network cut off.

Any attempt to open a socket fails the test. This backs the promise that the
original text never leaves the machine before it is anonymized.
"""

import socket

import pytest

from anon.cli import main


class NetworkUsed(AssertionError):
    pass


@pytest.fixture
def no_network(monkeypatch):
    def guard(*args, **kwargs):
        raise NetworkUsed("network access attempted")

    monkeypatch.setattr(socket.socket, "connect", guard)
    monkeypatch.setattr(socket.socket, "connect_ex", guard)
    monkeypatch.setattr(socket, "create_connection", guard)
    monkeypatch.setattr(socket, "getaddrinfo", guard)


@pytest.mark.models
def test_scan_apply_restore_offline(tmp_path, monkeypatch, no_network):
    monkeypatch.setenv("ANON_PASSWORD", "test-password")
    monkeypatch.setenv("ANON_LANG", "en")
    src = tmp_path / "interview.md"
    src.write_text(
        "Я Мария Ковалева, работаю в ООО «Северный ветер» в Твери, телефон +7 912 345-67-89.\n\n"
        "Звонила Ковалевой коллега Анна Смирнова.\n",
        encoding="utf-8",
    )
    main(["--project", str(tmp_path), "scan", str(src)])
    main(["--project", str(tmp_path), "apply"])
    out = (tmp_path / "interview.anon.md").read_text(encoding="utf-8")
    for secret in ("Ковалев", "Северный ветер", "Твер", "345-67-89", "Смирнов"):
        assert secret not in out
    answer = tmp_path / "answer.md"
    answer.write_text("Свяжитесь с [ИМЯ_1] из [ОРГ_1].", encoding="utf-8")
    main(["--project", str(tmp_path), "restore", str(answer)])
    restored = (tmp_path / "answer.restored.md").read_text(encoding="utf-8")
    assert restored == "Свяжитесь с Мария Ковалева из ООО «Северный ветер»."


@pytest.mark.models
def test_value_kept_in_one_file_is_hidden_in_all(tmp_path, monkeypatch, no_network):
    """A value found only in file A must still be replaced where detectors miss it in file B."""
    monkeypatch.setenv("ANON_PASSWORD", "pw")
    monkeypatch.setenv("ANON_LANG", "en")
    a = tmp_path / "a.md"
    b = tmp_path / "b.md"
    a.write_text("Я говорил с Марией Ковалевой из Казани.\n", encoding="utf-8")
    b.write_text("потом ковалева перезвонила\n", encoding="utf-8")  # lowercase: NER misses it
    main(["--project", str(tmp_path), "scan", str(a), str(b)])
    main(["--project", str(tmp_path), "apply"])
    out_b = (tmp_path / "b.anon.md").read_text(encoding="utf-8")
    assert "ковалев" not in out_b.lower()
