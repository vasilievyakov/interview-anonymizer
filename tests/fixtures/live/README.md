# Live-like synthetic set

A second synthetic corpus for `scripts/bench.py`. The first set (`tests/fixtures/ru`, `tests/fixtures/en`) is clean and well-formed; this one reproduces what real research interviews look like, so before/after numbers can be shown and reproduced without any real data.

```
uv run python scripts/bench.py --dir tests/fixtures/live
uv run python scripts/bench.py --dir tests/fixtures/live --keep tests/fixtures/live/keep.txt
```

## Contents

- `corpus/`: one description file with the sample table and six interview transcripts from two invented studies: user interviews about a fitness app (ПульсПлан against Ритмо and FitBox) and a taste and price study of grocery delivery chains (Лавка у дома, Корзинка, СвежаК) and their own brands. Five transcripts are in Russian, one is a short English interview.
- `golden/`: one JSON per corpus file, `{"file", "entities": [{"id", "kind", "tier", "role", "surfaces"}]}`. Tier `direct`: private persons, contacts, interview ids. Tier `quasi`: employers, small towns, districts, metro stations, schools, local gyms. Tier `public`: researched brands and products, big public chains, big cities, countries. Every surface is a verbatim substring of its file; `tests/test_live_fixtures.py` checks that.
- `keep.txt`: the researched brands and products, as `anon keep` would write them.

## Difficulties it contains

- Speaker headers glued to names (`0:07:03 - Олег (Speaker A): ...`), `[Speaker 1]` tags, a `## Сводка` block with name, age and city.
- Raw speech-to-text without punctuation where every phrase starts with a capital letter, filler words, lowercase names, two spellings of one surname.
- Brands distorted by speech-to-text (`Ритма`, `Рыдмо`, `Фит бокс`, `Свежак`) and product names that read like personal names (`Гуру`, `Добрыня`, `Шеф Классик`).
- One person under a full name, diminutives, a lone surname and other grammatical cases.
- Employers in several cases and once in lowercase speech; districts and metro stations; a former employer that is a big public chain; a metro station that collides with a product name.
- A markdown table of the sample; generic abbreviations (HR, ИП, ООО, МФЦ, IT) that are not organisations; interview ids like `Инт.12_Hs5nJd`.

## Everything is invented

All people, employers, contacts, ids, apps, chains and products are fictional. Real places appear only as places (big cities, a few small towns, districts and metro stations), never together with a real person. No sentence comes from a real interview.
