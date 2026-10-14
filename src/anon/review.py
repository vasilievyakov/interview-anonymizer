"""Human review of what the detectors found.

Findings from all files are grouped into one item per entity (all forms of
"Мария Ковалева" together), written to review.csv, and either walked through
in the terminal or edited in any spreadsheet. Decisions go into the vault and
are reused for every next file of the project.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path

from .i18n import t
from .model import Kind
from .names import name_key
from .vault import Vault, fold

REVIEW_FILE = "review.csv"
COLUMNS = ["keep", "kind", "text", "count", "variants", "files", "sources", "context"]
_YES = {"yes", "y", "да", "д", "1", "true", "+"}
_NO = {"no", "n", "нет", "н", "0", "false", "-"}


@dataclass
class Item:
    kind: Kind
    text: str  # the longest surface, shown to the human
    keep: bool = True
    count: int = 0
    variants: set[str] = field(default_factory=set)
    files: set[str] = field(default_factory=set)
    sources: set[str] = field(default_factory=set)
    context: str = ""


def group_key(kind: Kind, text: str, normal: str = "") -> tuple[str, str]:
    base = normal or text
    return kind.value, (name_key(base) if kind == Kind.PERSON else fold(base))


def context_of(text: str, start: int, end: int, width: int = 40) -> str:
    a, b = max(0, start - width), min(len(text), end + width)
    return " ".join(text[a:b].split())


class Collector:
    """Accumulates findings from many files into review items."""

    def __init__(self) -> None:
        self._items: dict[tuple[str, str], Item] = {}

    def add(
        self,
        kind: Kind,
        text: str,
        file: str,
        sources: list[str] | tuple[str, ...],
        context: str,
        normal: str = "",
    ) -> None:
        key = group_key(kind, text, normal)
        item = self._items.get(key)
        if item is None:
            item = self._items[key] = Item(kind=kind, text=text, context=context)
        item.count += 1
        item.variants.add(text)
        item.files.add(file)
        item.sources.update(sources)
        if len(text) > len(item.text):
            item.text = text

    def items(self) -> list[Item]:
        return sorted(
            self._items.values(), key=lambda i: (i.kind.value, -i.count, i.text)
        )


def write_csv(items: list[Item], path: Path) -> None:
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(COLUMNS)
        for i in items:
            w.writerow(
                [
                    "yes" if i.keep else "no",
                    i.kind.value,
                    i.text,
                    i.count,
                    " | ".join(sorted(i.variants)),
                    " | ".join(sorted(i.files)),
                    ",".join(sorted(i.sources)),
                    i.context,
                ]
            )


def read_csv(path: Path) -> list[Item]:
    items: list[Item] = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            mark = (row.get("keep") or "yes").strip().lower()
            items.append(
                Item(
                    kind=Kind((row.get("kind") or "PERSON").strip().upper()),
                    text=(row.get("text") or "").strip(),
                    keep=mark not in _NO,
                    count=int(row.get("count") or 0),
                    variants={
                        v.strip()
                        for v in (row.get("variants") or "").split("|")
                        if v.strip()
                    },
                    files={
                        v.strip()
                        for v in (row.get("files") or "").split("|")
                        if v.strip()
                    },
                    sources={
                        v.strip()
                        for v in (row.get("sources") or "").split(",")
                        if v.strip()
                    },
                    context=row.get("context") or "",
                )
            )
    return [i for i in items if i.text]


_KIND_CHOICES = {"1": Kind.PERSON, "2": Kind.ORG, "3": Kind.LOCATION, "4": Kind.ID}


def _safe(ask):
    """No terminal input (EOF, e.g. a non-interactive shell) reads as "q": stop, keep decisions so far."""

    def wrapped(prompt: str) -> str:
        try:
            return ask(prompt)
        except EOFError:
            return "q"

    return wrapped


def interactive(items: list[Item], ask=input, say=print) -> list[Item]:
    """Walk the items in the terminal. Returns the list with decisions and hand-added items."""
    ask = _safe(ask)
    say(t("review_header"))
    # Values already decided (earlier runs, the keep list) are not asked again.
    todo = [i for i in items if i.keep]
    if len(todo) < len(items):
        say(t("review_skipped", n=len(items) - len(todo)))
    total = len(todo)
    for n, item in enumerate(todo, 1):
        say(
            t(
                "review_item",
                i=n,
                total=total,
                kind=item.kind.value,
                text=item.text,
                count=item.count,
                sources=",".join(sorted(item.sources)),
                context=item.context,
            )
        )
        answer = ask("> ").strip().lower()
        if answer in ("q", "й"):
            break
        item.keep = answer not in _NO
    while True:
        text = ask(t("review_add")).strip()
        if not text or text == "q":
            break
        kind = _KIND_CHOICES.get(ask(t("review_add_kind")).strip() or "1", Kind.PERSON)
        items.append(
            Item(
                kind=kind,
                text=text,
                keep=True,
                variants={text},
                sources={"user"},
                context="",
            )
        )
    return items


def apply_decisions(items: list[Item], vault: Vault) -> tuple[int, int, int]:
    """Store decisions in the vault. Returns (kept, skipped, added by hand)."""
    kept = skipped = added = 0
    for item in items:
        surfaces = item.variants | {item.text}
        if not item.keep:
            skipped += 1
            vault.ignored.update(fold(s) for s in surfaces)
            continue
        kept += 1
        vault.ignored.difference_update(fold(s) for s in surfaces)
        if "user" in item.sources:
            added += 1
            for s in surfaces:
                if (s, item.kind) not in vault.added:
                    vault.added.append((s, item.kind))
    return kept, skipped, added
