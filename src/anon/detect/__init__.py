"""Detection: rules + NER layers, merged into one list of spans."""

from __future__ import annotations

from collections.abc import Iterable

from ..model import Finding, Merged
from .merge import merge

ALL_LAYERS = ("rules", "natasha", "spacy")

__all__ = ["ALL_LAYERS", "find_all", "merge"]


def _find_rules(text: str, langs: list[str]) -> list[Finding]:
    from .rules import find_rules  # imported lazily: rules.py is a separate module

    return find_rules(text, langs)


def find_all(
    text: str, langs: list[str] | None = None, layers: Iterable[str] = ALL_LAYERS
) -> list[Merged]:
    """Every sensitive span in text from the chosen layers, merged and sorted by start."""
    layers = tuple(layers)
    if langs is None:
        from ..lang import languages

        langs = languages(text)
    findings: list[Finding] = []
    if "rules" in layers:
        from .mdtable import find_tables

        findings.extend(_find_rules(text, langs))
        findings.extend(find_tables(text))
    ner_layers = tuple(x for x in layers if x in ("natasha", "spacy"))
    if ner_layers:
        from .ner import find_ner

        findings.extend(find_ner(text, langs, ner_layers))
    return merge(findings, text)
