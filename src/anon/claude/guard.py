#!/usr/bin/env python3
"""Claude Code PreToolUse hook: keep the original data out of the agent's context.

Blocks Read, Grep, Glob, Edit, Write (and MultiEdit, NotebookEdit) and Bash
readers (cat, head, tail, less, grep, rg, sed, awk, python -c open(...), cp,
open) when they touch:

- the files listed in .anon/scan.json of the project;
- an original file whose anonymized twin exists next to it (interview.md when
  interview.anon.md is there), so originals stay closed after anon apply
  removes scan.json;
- review.csv, anything under .anon/, any *.restored.* file.

*.anon.* files are allowed: they are what the agent works with.

Input: the hook JSON on stdin (tool_name, tool_input, cwd). Blocking is exit
code 2 with the reason on stderr; the reason never quotes a path, since file
names can carry a respondent's name. Malformed input: blocked when it mentions
review.csv, .anon/ or *.restored.*, allowed otherwise, with a note on stderr.

Python standard library only.
"""

from __future__ import annotations

import glob
import json
import os
import re
import shlex
import sys
from pathlib import Path

VAULT_DIR = ".anon"
REVIEW = "review.csv"
SCAN_STATE = "scan.json"
DATA_EXT = {".md", ".txt", ".docx", ".xlsx", ".csv"}
FILE_TOOLS = {"Read", "Edit", "Write", "MultiEdit", "NotebookEdit"}
READERS = {
    "cat", "head", "tail", "less", "more", "bat", "nl",
    "grep", "egrep", "fgrep", "rg", "sed", "awk", "gawk",
    "python", "python3", "cp", "open",
}  # fmt: skip
RECURSIVE = {"grep", "egrep", "fgrep", "rg", "cp"}
SEPARATORS = {"|", "||", "&&", ";", "&", "|&", ";;", "(", ")"}
SKIP_DIRS = {".git", "node_modules", ".venv", "__pycache__"}
WALK_LIMIT = 5000
GLOB_LIMIT = 5000

# Raw mentions that are enough to block when the input cannot be parsed.
_RAW_SENSITIVE = re.compile(
    r"review\.csv|\.restored\.|(?:^|[/\\\"'\s(=])\.anon(?:[/\\\"'\s)]|$)"
)
_ANON_DIR = re.compile(r"(?:^|[/\"'\s(=])\.anon(?:[/\"'\s)]|$)")
_QUOTED = re.compile(r"""['"]([^'"]+)['"]""")

R_VAULT = "the .anon/ folder holds the vault and the scan state with real values"
R_REVIEW = "review.csv holds the real values for the human review"
R_RESTORED = "*.restored.* files hold the real values put back"
R_SOURCE = "this is an original file being anonymized; only *.anon.* files may be read"
R_DIR = "this folder holds original data (originals, review.csv, .anon/ or *.restored.*); point the tool at the *.anon.* files"
R_SHOW = "ANON_SHOW_VALUES would print real values into the agent's context"


def note(message: str) -> None:
    print(f"anon guard: {message}", file=sys.stderr)


def block(reason: str) -> None:
    print(
        f"Blocked by the anon guard: {reason}. Work only with *.anon.* files; "
        "the person reviews values outside the agent.",
        file=sys.stderr,
    )
    sys.exit(2)


class Project:
    def __init__(self, cwd: Path) -> None:
        self.cwd = cwd
        roots = {cwd}
        env_root = os.environ.get("CLAUDE_PROJECT_DIR")
        if env_root:
            roots.add(Path(env_root).resolve())
        self.sources: set[Path] = set()
        for root in roots:
            self.sources |= _load_sources(root)

    def resolve(self, p: str) -> Path:
        path = Path(os.path.expanduser(p))
        if not path.is_absolute():
            path = self.cwd / path
        return path.resolve()

    def file_reason(self, path: Path) -> str | None:
        """Why this path must stay closed, or None."""
        if VAULT_DIR in path.parts:
            return R_VAULT
        if path.name == REVIEW:
            return R_REVIEW
        if ".restored." in path.name:
            return R_RESTORED
        if ".anon." in path.name:
            return None
        if path in self.sources or _has_anon_twin(path):
            return R_SOURCE
        return None

    def dir_reason(self, d: Path) -> str | None:
        if (d / REVIEW).exists() or (d / VAULT_DIR).exists():
            return R_DIR
        if any(d == s.parent or d in s.parents for s in self.sources):
            return R_DIR
        seen = 0
        for top, dirs, files in os.walk(d):
            if VAULT_DIR in dirs:
                return R_DIR
            dirs[:] = [x for x in dirs if x not in SKIP_DIRS]
            for name in files:
                seen += 1
                if seen > WALK_LIMIT:
                    note(f"folder too large to check fully ({WALK_LIMIT}+ files)")
                    return None
                if self.file_reason(Path(top) / name):
                    return R_DIR
        return None

    def path_reason(self, path: Path, as_dir: bool = True) -> str | None:
        reason = self.file_reason(path)
        if reason or not as_dir or not path.is_dir():
            return reason
        return self.dir_reason(path)

    def glob_reason(self, pattern: str, base: Path) -> str | None:
        full = pattern if os.path.isabs(pattern) else str(base / pattern)
        for n, hit in enumerate(glob.iglob(full, recursive=True)):
            if n > GLOB_LIMIT:
                note(f"pattern matches too many files to check ({GLOB_LIMIT}+)")
                return None
            reason = self.file_reason(Path(hit).resolve())
            if reason:
                return reason
        return None


def _load_sources(root: Path) -> set[Path]:
    state = root / VAULT_DIR / SCAN_STATE
    if not state.exists():
        return set()
    try:
        files = json.loads(state.read_text(encoding="utf-8"))["files"]
        return {Path(p).resolve() for p in files}
    except (OSError, ValueError, KeyError, TypeError):
        note("cannot read .anon/scan.json, the list of originals is not checked")
        return set()


def _has_anon_twin(path: Path) -> bool:
    suffix = path.suffix.lower()
    if suffix not in DATA_EXT:
        return False
    twin_ext = ".md" if suffix == ".docx" else path.suffix
    return path.with_name(f"{path.stem}.anon{twin_ext}").exists()


# ---- tools ----------------------------------------------------------------


def check_file_tool(tool: str, data: dict, project: Project) -> str | None:
    p = data.get("notebook_path" if tool == "NotebookEdit" else "file_path")
    if not isinstance(p, str) or not p:
        return None
    return project.path_reason(project.resolve(p), as_dir=False)


def check_grep(data: dict, project: Project) -> str | None:
    p = data.get("path")
    target = project.resolve(p) if isinstance(p, str) and p else project.cwd
    reason = project.file_reason(target)
    if reason:
        return reason
    pattern = data.get("glob")
    if isinstance(pattern, str) and ".anon." in pattern:
        return None
    return project.dir_reason(target) if target.is_dir() else None


def check_glob(data: dict, project: Project) -> str | None:
    p = data.get("path")
    base = project.resolve(p) if isinstance(p, str) and p else project.cwd
    pattern = data.get("pattern")
    if not isinstance(pattern, str) or not pattern:
        return None
    if _RAW_SENSITIVE.search(pattern):
        return R_DIR
    return project.file_reason(base) or project.glob_reason(pattern, base)


def _tokens(command: str) -> list[str]:
    try:
        lex = shlex.shlex(command, posix=True, punctuation_chars=True)
        lex.whitespace_split = True
        return list(lex)
    except ValueError:
        return command.split()


def _segments(tokens: list[str]) -> list[list[str]]:
    out: list[list[str]] = [[]]
    for tok in tokens:
        if tok in SEPARATORS:
            out.append([])
        else:
            out[-1].append(tok)
    return [s for s in out if s]


def _word_reason(word: str, project: Project, recursive: bool) -> str | None:
    if REVIEW in word:
        return R_REVIEW
    if ".restored." in word:
        return R_RESTORED
    if _ANON_DIR.search(word):
        return R_VAULT
    candidates = [word]
    if word.startswith("-"):
        candidates = [word.split("=", 1)[1]] if "=" in word else []
    candidates += _QUOTED.findall(word)  # paths inside python -c "open('...')"
    for cand in candidates:
        if not cand or ".anon." in cand:
            continue
        if any(ch in cand for ch in "*?["):
            reason = project.glob_reason(cand, project.cwd)
        else:
            try:
                path = project.resolve(cand)
                exists = path.exists()
            except (OSError, ValueError, RuntimeError):
                continue
            reason = project.path_reason(path, as_dir=recursive) if exists else None
        if reason:
            return reason
    return None


def check_bash(data: dict, project: Project) -> str | None:
    command = data.get("command")
    if not isinstance(command, str):
        return None
    if "ANON_SHOW_VALUES" in command:
        return R_SHOW
    for seg in _segments(_tokens(command)):
        names = [os.path.basename(w) for w in seg]
        readers = [n for n in names if n in READERS]
        if not readers:
            continue
        recursive = any(n in RECURSIVE for n in readers)
        for word in seg:
            reason = _word_reason(word, project, recursive)
            if reason:
                return reason
        greps = {"grep", "egrep", "fgrep"} & set(readers)
        searches_cwd = "rg" in readers or (
            greps and any(_recursive_flag(w) for w in seg)
        )
        if searches_cwd and not any(_names_path(w, project) for w in seg):
            # rg and grep -r without a path search the current folder.
            reason = project.dir_reason(project.cwd)
            if reason:
                return reason
    return None


def _recursive_flag(word: str) -> bool:
    if word.startswith("--"):
        return word in ("--recursive", "--dereference-recursive")
    return word.startswith("-") and ("r" in word or "R" in word)


def _names_path(word: str, project: Project) -> bool:
    if word.startswith("-") or os.path.basename(word) in READERS:
        return False
    if ".anon." in word:
        return True
    try:
        return project.resolve(word).exists()
    except (OSError, ValueError, RuntimeError):
        return False


def main() -> None:
    raw = sys.stdin.read()
    try:
        event = json.loads(raw)
        tool = event["tool_name"]
        data = event.get("tool_input") or {}
        if not isinstance(data, dict):
            raise TypeError("tool_input is not an object")
    except (ValueError, KeyError, TypeError):
        if _RAW_SENSITIVE.search(raw):
            block(
                "could not parse the hook input, and it mentions review.csv, .anon/ or *.restored.*"
            )
        note("could not parse the hook input, call allowed")
        return
    try:
        project = Project(Path(event.get("cwd") or os.getcwd()).resolve())
        if tool in FILE_TOOLS:
            reason = check_file_tool(tool, data, project)
        elif tool == "Grep":
            reason = check_grep(data, project)
        elif tool == "Glob":
            reason = check_glob(data, project)
        elif tool == "Bash":
            reason = check_bash(data, project)
        else:
            reason = None
    except Exception as exc:  # noqa: BLE001  a bug here must not lock the agent out of everything
        if _RAW_SENSITIVE.search(json.dumps(data, ensure_ascii=False)):
            block(
                "internal error while checking a call that mentions review.csv, .anon/ or *.restored.*"
            )
        note(f"internal error ({type(exc).__name__}), call allowed")
        return
    if reason:
        block(reason)


if __name__ == "__main__":
    main()
