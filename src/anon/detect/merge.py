"""Union of detector layers into one span per place in the text."""

from __future__ import annotations

from ..model import Finding, Merged

# Higher first. "user" and "column" come from review and tables and outrank detectors.
PRIORITY = ("user", "column", "rules", "natasha", "spacy")


def _rank(source: str) -> int:
    try:
        return PRIORITY.index(source)
    except ValueError:
        return len(PRIORITY)


def _build(group: list[Finding], text: str) -> Merged:
    start = min(f.start for f in group)
    end = max(f.end for f in group)
    # Highest-priority source first; within it, the earliest (then longest) finding.
    ordered = sorted(group, key=lambda f: (_rank(f.source), f.start, -(f.end - f.start)))
    kind = ordered[0].kind
    normal = next((f.normal for f in ordered if f.normal), "")
    sources = sorted({f.source for f in group}, key=lambda s: (_rank(s), s))
    return Merged(
        start=start,
        end=end,
        text=text[start:end],
        kind=kind,
        sources=sources,
        normal=normal,
    )


def merge(findings: list[Finding], text: str) -> list[Merged]:
    """Merge overlapping findings of all layers.

    Spans that share at least one character become one Merged covering their
    union; spans that merely touch (one ends where the next starts) stay apart.
    Kind and normal come from the highest-priority layer (user > column >
    rules > natasha > spacy). `sources` lists every layer that hit, in
    priority order. Result is sorted by start.
    """
    items = sorted(
        (f for f in findings if f.end > f.start), key=lambda f: (f.start, -f.end)
    )
    out: list[Merged] = []
    group: list[Finding] = []
    group_end = -1
    for f in items:
        if group and f.start < group_end:
            group.append(f)
            group_end = max(group_end, f.end)
            continue
        if group:
            out.append(_build(group, text))
        group, group_end = [f], f.end
    if group:
        out.append(_build(group, text))
    return out
