"""Shared data types. Every module talks in these terms."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Kind(str, Enum):
    PERSON = "PERSON"
    ORG = "ORG"
    LOCATION = "LOCATION"
    PHONE = "PHONE"
    EMAIL = "EMAIL"
    SNILS = "SNILS"
    INN = "INN"
    PASSPORT = "PASSPORT"
    CARD = "CARD"
    SSN = "SSN"
    NINO = "NINO"
    ID = "ID"  # employee/personnel numbers and other identifier columns


# Tag that appears inside a label, per output language: [ИМЯ_1] / [PERSON_1].
LABEL_TAGS: dict[str, dict[Kind, str]] = {
    "ru": {
        Kind.PERSON: "ИМЯ",
        Kind.ORG: "ОРГ",
        Kind.LOCATION: "МЕСТО",
        Kind.PHONE: "ТЕЛЕФОН",
        Kind.EMAIL: "ПОЧТА",
        Kind.SNILS: "СНИЛС",
        Kind.INN: "ИНН",
        Kind.PASSPORT: "ПАСПОРТ",
        Kind.CARD: "КАРТА",
        Kind.SSN: "SSN",
        Kind.NINO: "NINO",
        Kind.ID: "НОМЕР",
    },
    "en": {
        Kind.PERSON: "PERSON",
        Kind.ORG: "ORG",
        Kind.LOCATION: "LOCATION",
        Kind.PHONE: "PHONE",
        Kind.EMAIL: "EMAIL",
        Kind.SNILS: "SNILS",
        Kind.INN: "INN",
        Kind.PASSPORT: "PASSPORT",
        Kind.CARD: "CARD",
        Kind.SSN: "SSN",
        Kind.NINO: "NINO",
        Kind.ID: "ID",
    },
}


@dataclass(frozen=True)
class Finding:
    """One sensitive span found in a text.

    start/end are character offsets into the analysed string (end exclusive).
    source is the layer that produced it: "rules", "natasha", "spacy", "column", "user".
    normal is the canonical form used to group variants of one entity
    (e.g. "Марией Ковалевой" -> "мария ковалева"); empty means "use text".
    """

    start: int
    end: int
    text: str
    kind: Kind
    source: str
    normal: str = ""

    @property
    def key_text(self) -> str:
        return self.normal or self.text


@dataclass
class Merged:
    """A span after merging layers: one place in the text, possibly found by several layers."""

    start: int
    end: int
    text: str
    kind: Kind
    sources: list[str] = field(default_factory=list)
    normal: str = ""
