"""The vault: the only place where labels map back to real values.

It lives in the project folder (`.anon/vault.bin`), encrypted with a password
(scrypt -> Fernet). Without the password the file is opaque bytes.

One vault per project, so the same person gets the same label in every file.
"""

from __future__ import annotations

import base64
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

from .model import LABEL_TAGS, Kind

VAULT_DIR = ".anon"
VAULT_FILE = "vault.bin"
_MAGIC = b"ANON1"
_SALT_LEN = 16


class VaultError(Exception):
    pass


def _fernet(password: str, salt: bytes) -> Fernet:
    kdf = Scrypt(salt=salt, length=32, n=2**15, r=8, p=1)
    key = base64.urlsafe_b64encode(kdf.derive(password.encode("utf-8")))
    return Fernet(key)


def fold(s: str) -> str:
    """Comparison form: lowercase, ё -> е, collapsed whitespace, unified quotes."""
    s = s.lower().replace("ё", "е")
    s = re.sub(r"[«»\"“”„']", '"', s)
    return re.sub(r"\s+", " ", s).strip()


@dataclass
class Entity:
    key: int  # number inside the label
    kind: Kind
    canonical: str  # how restore writes it back
    variants: set[str] = field(default_factory=set)  # folded surfaces and normals seen


@dataclass
class Vault:
    entities: list[Entity] = field(default_factory=list)
    # Review decisions, reused for every next file of the project.
    ignored: set[str] = field(
        default_factory=set
    )  # folded strings that are not sensitive
    added: list[tuple[str, Kind]] = field(
        default_factory=list
    )  # strings the human marked as sensitive

    # ---- lookup -------------------------------------------------------

    def find(self, kind: Kind, *texts: str) -> Entity | None:
        folded = {fold(t) for t in texts if t}
        for e in self.entities:
            if e.kind == kind and e.variants & folded:
                return e
        return None

    def label(self, entity: Entity, lang: str) -> str:
        return f"[{LABEL_TAGS[lang][entity.kind]}_{entity.key}]"

    def get_or_create(
        self, kind: Kind, surface: str, normal: str = "", canonical: str = ""
    ) -> Entity:
        """Entity for this value; creates a new numbered one when unseen."""
        e = self.find(kind, surface, normal)
        if e is None:
            n = 1 + max((x.key for x in self.entities if x.kind == kind), default=0)
            e = Entity(key=n, kind=kind, canonical=canonical or normal or surface)
            self.entities.append(e)
        e.variants.add(fold(surface))
        if normal:
            e.variants.add(fold(normal))
        return e

    def is_ignored(self, text: str) -> bool:
        return fold(text) in self.ignored

    def secrets(self) -> list[str]:
        """Every real value the vault knows. Leak check searches outputs for these."""
        out: set[str] = set()
        for e in self.entities:
            out.add(e.canonical)
            out.update(e.variants)
        return sorted(out, key=len, reverse=True)

    def labels(self) -> dict[str, Entity]:
        """Every label in both languages -> entity. Used by restore."""
        out: dict[str, Entity] = {}
        for e in self.entities:
            for lang in LABEL_TAGS:
                out[self.label(e, lang)] = e
        return out

    # ---- persistence --------------------------------------------------

    def to_json(self) -> dict:
        return {
            "entities": [
                {
                    "key": e.key,
                    "kind": e.kind.value,
                    "canonical": e.canonical,
                    "variants": sorted(e.variants),
                }
                for e in self.entities
            ],
            "ignored": sorted(self.ignored),
            "added": [[t, k.value] for t, k in self.added],
        }

    @classmethod
    def from_json(cls, data: dict) -> "Vault":
        return cls(
            entities=[
                Entity(
                    key=d["key"],
                    kind=Kind(d["kind"]),
                    canonical=d["canonical"],
                    variants=set(d["variants"]),
                )
                for d in data.get("entities", [])
            ],
            ignored=set(data.get("ignored", [])),
            added=[(t, Kind(k)) for t, k in data.get("added", [])],
        )

    def save(self, project: Path, password: str) -> Path:
        path = Path(project) / VAULT_DIR / VAULT_FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        salt = os.urandom(_SALT_LEN)
        token = _fernet(password, salt).encrypt(
            json.dumps(self.to_json(), ensure_ascii=False).encode("utf-8")
        )
        tmp = path.with_suffix(".tmp")
        tmp.write_bytes(_MAGIC + salt + token)
        os.chmod(tmp, 0o600)
        tmp.replace(path)
        return path

    @classmethod
    def load(cls, project: Path, password: str) -> "Vault":
        path = Path(project) / VAULT_DIR / VAULT_FILE
        if not path.exists():
            return cls()
        raw = path.read_bytes()
        if not raw.startswith(_MAGIC):
            raise VaultError(f"{path}: not a vault file")
        salt = raw[len(_MAGIC) : len(_MAGIC) + _SALT_LEN]
        try:
            data = _fernet(password, salt).decrypt(raw[len(_MAGIC) + _SALT_LEN :])
        except InvalidToken as exc:
            raise VaultError("wrong password") from exc
        return cls.from_json(json.loads(data))

    @staticmethod
    def exists(project: Path) -> bool:
        return (Path(project) / VAULT_DIR / VAULT_FILE).exists()
