"""Put real values back in place of labels in a model's answer.

Exact labels (`[ИМЯ_1]`, `[PERSON_1]`) are replaced silently. Damaged forms
that models tend to produce are accepted too, and each one is reported so the
human can check the result:

- wrong case: `[имя_1]`, `[Имя_1]`;
- missing brackets: `ИМЯ_1` (underscore required, word boundaries);
- space instead of underscore or padding: `[ИМЯ 1]`, `[ ИМЯ_1 ]`;
- a Russian case ending glued to the label: `[ИМЯ_1]-ой`, `[ИМЯ_1]ой`
  (the ending is dropped, the grammar around it needs a human look).

Labels with a known tag but a number the vault does not have are left as is
and reported.
"""

from __future__ import annotations

import bisect
import re

from .i18n import t
from .model import LABEL_TAGS
from .vault import Vault

_TAGS = sorted(
    {t for tags in LABEL_TAGS.values() for t in tags.values()}, key=len, reverse=True
)
_TAG_ALT = "|".join(map(re.escape, _TAGS))

# A glued Russian case ending: up to three Cyrillic letters, optional hyphen,
# and no more letters right after it (so a glued word is not eaten).
_ENDING = r"(?:(?P<end>-?[а-яё]{1,3})(?![^\W\d_]))?"

_PATTERN = re.compile(
    r"(?:"
    rf"\[(?P<bpad1>\s*)(?P<btag>{_TAG_ALT})(?P<bsep>_|\s+)(?P<bnum>\d+)(?P<bpad2>\s*)\]"
    r"|"
    rf"(?<![\w\[])(?P<tag>{_TAG_ALT})_(?P<num>\d+)(?![\d\]])"
    r")" + _ENDING,
    re.IGNORECASE,
)


def _line_starts(text: str) -> list[int]:
    starts = [0]
    starts.extend(i + 1 for i, ch in enumerate(text) if ch == "\n")
    return starts


def restore(text: str, vault: Vault) -> tuple[str, list[str]]:
    """Replace labels with canonical values. Returns (text, problems)."""
    labels = vault.labels()
    starts = _line_starts(text)
    problems: list[str] = []
    out: list[str] = []
    pos = 0

    for m in _PATTERN.finditer(text):
        line = bisect.bisect_right(starts, m.start())
        whole = m.group(0)
        bracketed = m.group("btag") is not None
        tag = m.group("btag") if bracketed else m.group("tag")
        num = m.group("bnum") if bracketed else m.group("num")
        ending = m.group("end")
        label = f"[{tag.upper()}_{int(num)}]"
        entity = labels.get(label)

        if entity is None:
            if ending:
                # The ending is not part of the label; leave it out of the report.
                whole = whole[: -len(ending)]
            problems.append(t("restore_unknown", line=line, whole=whole))
            continue

        reasons: list[str] = []
        if tag != tag.upper():
            reasons.append(t("restore_wrong_case"))
        if not bracketed:
            reasons.append(t("restore_missing_brackets"))
        else:
            if m.group("bsep") != "_":
                reasons.append(t("restore_space_sep"))
            if m.group("bpad1") or m.group("bpad2"):
                reasons.append(t("restore_extra_spaces"))
        if num != str(int(num)):
            reasons.append(t("restore_leading_zeros"))
        if ending:
            reasons.append(t("restore_case_ending", ending=ending))
        if reasons:
            problems.append(
                t("restore_read_as", line=line, whole=whole, label=label,
                  value=entity.canonical, reasons="; ".join(reasons))
            )

        out.append(text[pos : m.start()])
        out.append(entity.canonical)
        pos = m.end()

    out.append(text[pos:])
    return "".join(out), problems
