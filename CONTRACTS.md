# Module contracts

Internal map for contributors. Every module talks in `anon.model` types.
Run tests with `uv run pytest`. Python 3.12 via uv, dependencies are already in `pyproject.toml`.

## Flow

```
input file -> lang.languages() -> detect.find_all() -> review -> replace.apply() -> leak check -> output
                                   (rules + natasha + spacy, merged)                         + vault (encrypted)
answer from the model -> restore.restore() -> answer with real values
```

## Owned by wave 0 (done, stable)

- `anon/model.py`: `Kind`, `LABEL_TAGS`, `Finding`, `Merged`.
- `anon/lang.py`: `detect(text) -> "ru"|"en"|"mixed"`, `languages(text) -> list[str]`, `label_language(text) -> "ru"|"en"`.
- `anon/vault.py`: `Vault` (`get_or_create(kind, surface, normal="", canonical="") -> Entity`, `label(entity, lang) -> "[ИМЯ_1]"`, `find`, `is_ignored`, `secrets()`, `labels()`, `save/load(project_dir, password)`), `fold(s)`.

## Wave 1

### A. Rules: `anon/detect/rules.py`

`find_rules(text: str, langs: list[str]) -> list[Finding]`, `source="rules"`.

- ru: PHONE (+7 / 8, with spaces, dashes, brackets), EMAIL, SNILS (checksum), INN 10 and 12 digits (checksum), PASSPORT (series+number, only near the word «паспорт»), CARD (Luhn, 13 to 19 digits).
- en: PHONE (US and UK formats), EMAIL, SSN (invalid areas 000, 666, 9xx rejected), NINO (UK National Insurance number), CARD (Luhn).
- Must not fire on amounts ("200000", "120 000"), dates, timestamps like `[00:02:33]`, years, percentages.

### B. NER and merge: `anon/detect/ner.py`, `anon/detect/merge.py`, `anon/detect/__init__.py`, `anon/names.py`

- `find_ner(text, langs, layers=("natasha", "spacy")) -> list[Finding]`: PERSON / ORG / LOCATION, `source` is `"natasha"` or `"spacy"`, `normal` filled with the nominative form where available. Natasha runs for ru only; spaCy uses `ru_core_news_sm` for ru and `en_core_web_sm` for en. Models load lazily, once per process.
- `merge(findings, text) -> list[Merged]`: union of all layers. Overlapping spans become one `Merged` covering the union; kind priority: user > column > rules > natasha > spacy. `sources` lists every layer that hit.
- `find_all(text, langs=None, layers=ALL_LAYERS) -> list[Merged]` in `anon/detect/__init__.py`: rules + ner, merged, sorted by start. `ALL_LAYERS = ("rules", "natasha", "spacy")`. `langs=None` means `lang.languages(text)`.
- `names.py`: `name_key(text) -> str` (case- and gender-insensitive identity key), `same_person(a, b) -> bool`. Oblique forms must collapse: "Ковалевой", "Ковалева", "Ковалев" -> one key.

### C. Tables: `anon/table.py`

- `scan_table(path) -> TableScan`: xlsx and csv. Classifies columns by header synonyms (ru and en) and by values (share of non-empty cells that `find_all` marks as one kind). Free-text cells in other columns go through `find_all`.
- `apply_table(path, scan, vault, out_path) -> None`: classified columns are replaced cell by cell with labels; free-text cells via `replace.apply`; numbers, dates and headers untouched; xlsx keeps sheets, formatting and formulas.
- Separate «Фамилия / Имя / Отчество» (First / Last name) columns form one PERSON per row; every part cell gets that person's label.
- `TableScan` exposes the items needed for review as `list[Merged]`-like records with a context string.

### D. Text, replace, restore: `anon/replace.py`, `anon/text.py`, `anon/restore.py`

- `replace.apply(text, spans: list[Merged], vault, lang) -> str`: replaces spans with labels from `vault.get_or_create`; PERSON identity uses `names.same_person` against existing PERSON entities; skips `vault.is_ignored`; also replaces `vault.added` strings and literal repeats of known vault variants that detectors missed (word-boundary, case-insensitive).
- `text.read_text(path) -> str` for .md, .txt, .docx; `text.write_text(path, s)`.
- `restore.restore(text, vault) -> tuple[str, list[str]]`: labels in either language back to `canonical`; tolerant to `[имя_1]`, `ИМЯ_1` without brackets, `[ИМЯ 1]`, labels with Russian case endings glued (`[ИМЯ_1]-ой`); every tolerant or unknown hit is listed in the problems list.

### E. Synthetic reference set: `tests/fixtures/`, `scripts/eval.py`

Invented data only. ru and en interviews and staff tables, every sensitive mention listed in `golden.json`, decoys that must stay. `scripts/eval.py` prints recall per layer and for the union, false hits, and leak count after `replace.apply`.

## Wave 2 (after wave 1)

`anon/review.py`, `anon/leak.py`, `anon/i18n.py`, `anon/cli.py` (`anon scan | review | apply | restore`), README in English and Russian.
