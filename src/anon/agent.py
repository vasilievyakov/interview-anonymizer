"""Agent-safe output.

Whatever a command prints inside Claude Code or Codex lands in the cloud
model's context. In that case (and whenever stdout is not a terminal) no
command prints a value from the data: only counts, kinds and line numbers.

ANON_SHOW_VALUES=1 turns it off for a person who pipes the output on purpose.
"""

from __future__ import annotations

import os
import sys


def quiet() -> bool:
    env = os.environ
    if env.get("ANON_SHOW_VALUES") == "1":
        return False
    if env.get("CLAUDECODE") or env.get("ANON_AGENT") == "1":
        return True
    if any(k.startswith("CODEX_") for k in env):
        return True
    try:
        return not sys.stdout.isatty()
    except (AttributeError, ValueError):
        return True
