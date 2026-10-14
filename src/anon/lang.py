"""Language detection by script share. Deterministic, no models."""

from __future__ import annotations

import re

_CYR = re.compile(r"[А-Яа-яЁё]")
_LAT = re.compile(r"[A-Za-z]")


def detect(text: str) -> str:
    """Return "ru", "en" or "mixed".

    "mixed" means both scripts carry real weight (each >= 20% of letters),
    so both detector sets must run.
    """
    cyr = len(_CYR.findall(text))
    lat = len(_LAT.findall(text))
    total = cyr + lat
    if total == 0:
        return "en"
    share = cyr / total
    if share >= 0.8:
        return "ru"
    if share <= 0.2:
        return "en"
    return "mixed"


def languages(text: str) -> list[str]:
    """Detector sets to run for this text."""
    lang = detect(text)
    return ["ru", "en"] if lang == "mixed" else [lang]


def label_language(text: str) -> str:
    """Language for label tags in the output: mixed texts get Russian tags."""
    return "en" if detect(text) == "en" else "ru"
