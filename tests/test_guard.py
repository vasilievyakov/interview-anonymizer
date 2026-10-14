"""anon/claude/guard.py: the PreToolUse hook keeps original data away from the agent."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

GUARD = Path(__file__).resolve().parents[1] / "src" / "anon" / "claude" / "guard.py"


@pytest.fixture
def project(tmp_path):
    (tmp_path / "interview.md").write_text("Я Мария Ковалева.\n", encoding="utf-8")
    (tmp_path / "staff.csv").write_text("ФИО\nМария Ковалева\n", encoding="utf-8")
    (tmp_path / "interview.anon.md").write_text("Я [ИМЯ_1].\n", encoding="utf-8")
    (tmp_path / "review.csv").write_text(
        "keep,kind,text\nyes,PERSON,Мария Ковалева\n", encoding="utf-8"
    )
    (tmp_path / "answer.restored.md").write_text("Мария Ковалева\n", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("plan\n", encoding="utf-8")
    state = tmp_path / ".anon"
    state.mkdir()
    (state / "vault.bin").write_bytes(b"x")
    (state / "scan.json").write_text(
        json.dumps(
            {"files": [str(tmp_path / "interview.md"), str(tmp_path / "staff.csv")]}
        ),
        encoding="utf-8",
    )
    sub = tmp_path / "work"
    sub.mkdir()
    (sub / "draft.anon.md").write_text("[ИМЯ_1]\n", encoding="utf-8")
    return tmp_path


def run(payload, cwd: Path | None = None) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k != "CLAUDE_PROJECT_DIR"}
    raw = (
        payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
    )
    return subprocess.run(
        [sys.executable, str(GUARD)],
        input=raw,
        capture_output=True,
        text=True,
        env=env,
        cwd=cwd,
        timeout=20,
        check=False,
    )


def call(project: Path, tool: str, **tool_input) -> subprocess.CompletedProcess:
    return run(
        {
            "session_id": "s",
            "hook_event_name": "PreToolUse",
            "cwd": str(project),
            "tool_name": tool,
            "tool_input": tool_input,
        }
    )


BLOCKED = [
    ("Read", {"file_path": "interview.md"}),
    ("Read", {"file_path": "staff.csv"}),
    ("Read", {"file_path": "review.csv"}),
    ("Read", {"file_path": ".anon/vault.bin"}),
    ("Read", {"file_path": ".anon/scan.json"}),
    ("Read", {"file_path": "answer.restored.md"}),
    ("Edit", {"file_path": "review.csv", "old_string": "yes", "new_string": "no"}),
    ("Write", {"file_path": "new.restored.md", "content": "x"}),
    ("Grep", {"pattern": "Мария"}),
    ("Grep", {"pattern": "Мария", "path": "interview.md"}),
    ("Grep", {"pattern": "Мария", "glob": "*.md"}),
    ("Glob", {"pattern": "*.md"}),
    ("Glob", {"pattern": ".anon/*"}),
    ("Bash", {"command": "cat interview.md"}),
    ("Bash", {"command": "head -n 5 review.csv"}),
    ("Bash", {"command": "tail answer.restored.md"}),
    ("Bash", {"command": "less staff.csv"}),
    ("Bash", {"command": "sed -n 1p .anon/scan.json"}),
    ("Bash", {"command": "awk '{print}' *.md"}),
    ("Bash", {"command": "grep -r Мария ."}),
    ("Bash", {"command": "grep -rn Мария"}),
    ("Bash", {"command": "rg Мария"}),
    ("Bash", {"command": "python3 -c \"print(open('interview.md').read())\""}),
    ("Bash", {"command": "cp interview.md /tmp/x.md"}),
    ("Bash", {"command": "open review.csv"}),
    ("Bash", {"command": "anon list | cat && cat interview.md"}),
    ("Bash", {"command": "ANON_SHOW_VALUES=1 anon list"}),
]

ALLOWED = [
    ("Read", {"file_path": "interview.anon.md"}),
    ("Read", {"file_path": "notes.txt"}),
    ("Write", {"file_path": "answer.md", "content": "[ИМЯ_1]"}),
    ("Grep", {"pattern": "ИМЯ", "path": "interview.anon.md"}),
    ("Grep", {"pattern": "ИМЯ", "glob": "*.anon.*"}),
    ("Grep", {"pattern": "ИМЯ", "path": "work"}),
    ("Glob", {"pattern": "*.anon.md"}),
    ("Glob", {"pattern": "work/*.md"}),
    ("Bash", {"command": "cat interview.anon.md"}),
    ("Bash", {"command": "rg ИМЯ interview.anon.md"}),
    ("Bash", {"command": "anon scan interview.md staff.csv"}),
    ("Bash", {"command": "anon apply"}),
    ("Bash", {"command": "anon restore answer.md"}),
    ("Bash", {"command": "ls -la"}),
    ("Bash", {"command": "cat notes.txt | head -3"}),
    ("WebSearch", {"query": "anything"}),
]


@pytest.mark.parametrize(("tool", "tool_input"), BLOCKED)
def test_blocked(project, tool, tool_input):
    result = call(project, tool, **tool_input)
    assert result.returncode == 2, result.stderr
    assert "anon guard" in result.stderr
    assert "Мария" not in result.stderr and "interview" not in result.stderr


@pytest.mark.parametrize(("tool", "tool_input"), ALLOWED)
def test_allowed(project, tool, tool_input):
    result = call(project, tool, **tool_input)
    assert result.returncode == 0, result.stderr


def test_absolute_paths(project):
    assert (
        call(project, "Read", file_path=str(project / "interview.md")).returncode == 2
    )
    assert (
        call(project, "Read", file_path=str(project / "interview.anon.md")).returncode
        == 0
    )


def test_original_stays_closed_after_apply(project):
    """anon apply removes scan.json; the *.anon.* twin still marks the original."""
    (project / ".anon" / "scan.json").unlink()
    assert call(project, "Read", file_path="interview.md").returncode == 2
    assert call(project, "Bash", command="cat interview.md").returncode == 2
    # staff.csv has no twin and is no longer listed: nothing marks it now
    assert call(project, "Read", file_path="staff.csv").returncode == 0


def test_docx_twin_is_markdown(project):
    (project / "call.docx").write_bytes(b"PK")
    assert call(project, "Read", file_path="call.docx").returncode == 0
    (project / "call.anon.md").write_text("[ИМЯ_1]", encoding="utf-8")
    assert call(project, "Read", file_path="call.docx").returncode == 2


def test_malformed_scan_state_fails_open_for_originals_only(project):
    (project / ".anon" / "scan.json").write_text("{broken", encoding="utf-8")
    result = call(project, "Read", file_path="staff.csv")
    assert result.returncode == 0
    assert "scan.json" in result.stderr
    assert call(project, "Read", file_path="review.csv").returncode == 2
    assert call(project, "Read", file_path=".anon/vault.bin").returncode == 2


def test_malformed_input(project):
    assert run("not json, Read review.csv").returncode == 2
    assert (
        run(
            '{"tool_name": "Read", "tool_input": {"file_path": ".anon/vault.bin"'
        ).returncode
        == 2
    )
    result = run("not json at all")
    assert result.returncode == 0
    assert "anon guard" in result.stderr


def test_cwd_falls_back_to_process(project):
    result = run(
        {"tool_name": "Read", "tool_input": {"file_path": "interview.md"}}, cwd=project
    )
    assert result.returncode == 2


def test_install_skill_copies_files_and_uses_this_python(tmp_path, monkeypatch, capsys):
    from anon import cli

    monkeypatch.setenv("CLAUDE_SKILLS_DIR", str(tmp_path))
    monkeypatch.setattr(sys, "argv", ["anon", "install-skill"])
    cli.main()
    dest = tmp_path / "anonymize"
    assert (dest / "SKILL.md").read_text(encoding="utf-8").startswith("---")
    assert (dest / "hooks" / "guard.py").exists()
    out = capsys.readouterr().out
    snippet = json.loads(out[out.index("{") :])
    command = snippet["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
    assert command == f'"{sys.executable}" "{dest / "hooks" / "guard.py"}"'
