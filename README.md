# Interview anonymizer

[Русская версия](README.ru.md)

An open tool from [AI Lab](https://ai-lab-agents.com), a lab on using AI agents in business. We built it for our own research and wrote it up as a case: how the first version met real interviews and what had to change is told in "How it was made".

`anon` hides personal data in interview transcripts and tables before you send them to a cloud LLM, then puts the real values back into the model's answer. Everything that touches the original data runs on your machine, without network access.

```
your computer                                                           cloud

 interview.md ─┐
 staff.xlsx  ──┤
               ▼
 anon keep ─> anon scan ─> anon review --web ─> anon apply ─> *.anon.* ──> any LLM
 brands that  rules,       a local page:        labels               │        │
 stay in the  Natasha,     you hide, keep,      + leak check         │        │
 text         spaCy        add what was missed        │              │        │
                                                      └─> .anon/vault.bin     │
                                                          (encrypted)         │
 answer.restored.md <──────────── anon restore <──────────── answer.md <──────┘
```

Russian and English. Tables: `.xlsx`, `.csv`. Texts: `.md`, `.txt`, `.docx`.

![The whole cycle in a terminal on invented interviews: keep, scan, apply, restore](docs/media/demo.gif)

## What the model sees

| Before | Sent to the model |
|---|---|
| I'm John Carter from Brightline Logistics in Leeds, call me on 07700 900123. | I'm [PERSON_1] from [ORG_1] in [LOCATION_1], call me on [PHONE_1]. |
| Я Мария Ковалева из ООО «Северный ветер» в Казани, +7 912 345-67-89. | Я [ИМЯ_1] из [ОРГ_1] в [МЕСТО_1], [ТЕЛЕФОН_1]. |

In tables, name, email, phone, ID and similar columns are replaced cell by cell. Numbers, dates and formulas stay as they are, so the model can still compute a budget. Names inside free-text cells (comments, notes) are found too.

The same person gets the same label in every file of a project and in every grammatical form: "Марией Ковалевой", "Ковалева" and "Мария Ковалева" all become `[ИМЯ_1]`.

## Install

You need [uv](https://docs.astral.sh/uv/). If you do not have it:

```sh
# macOS, Linux
curl -LsSf https://astral.sh/uv/install.sh | sh
```

```powershell
# Windows, PowerShell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Then:

```sh
uv tool install https://github.com/vasilievyakov/interview-anonymizer/archive/refs/heads/main.zip
anon --version
```

If the shell says `anon: command not found`, run `uv tool update-shell` and open a new terminal.

The link points to a zip archive, so neither git nor a system Python is needed: on a clean Mac both are stubs that ask to install the developer tools. `uv tool install git+https://github.com/vasilievyakov/interview-anonymizer` also works where git is installed.

- uv picks a suitable Python (3.11 to 3.14) and installs the language models with the tool.
- About 300 MB on disk and 0.8 GB of memory while it runs.
- The first run takes 10 to 25 seconds while the models load from disk; after that, about a second per command.
- After installation it works offline.
- Upgrade: `uv tool install --reinstall https://github.com/vasilievyakov/interview-anonymizer/archive/refs/heads/main.zip`. Remove: `uv tool uninstall interview-anonymizer`.
- Installed it before the rename? Find the old package in `uv tool list` and remove it with `uv tool uninstall <name>`.
- Windows on ARM is not supported: spaCy publishes no wheels for it.

## Use

Run the commands in the folder of your project: the vault is created there, in `.anon/`. Another folder can be named with `anon --project PATH ...`.

```sh
# 0. once per project: public names the research is about stay in the text
anon keep ПульсПлан Ритмо FitBox

# 1. find what looks personal and write review.csv
anon scan interview-01.md interview-02.md staff.xlsx

# 2. go through the findings on a local page in your browser
anon review --web

# 3. replace, run the leak check, write interview-01.anon.md and staff.anon.xlsx
anon apply

# 4. send the *.anon.* files to the model, save its answer, then
anon restore answer.md        # -> answer.restored.md
```

**Keep list.** `anon keep` lists the brands, products and services the research is about. They are matched in every grammatical form and in common speech-to-text distortions ("Фитбокс" for "FitBox", "Корзинко" for "Корзинка"), shown as already decided in the review and left in the text. Russian cities over a million people and countries are always kept; smaller towns, districts, streets and employers are not. `anon keep` without arguments prints the list.

**Review.** `anon review --web` opens a page on `127.0.0.1` with a one-time token; it loads nothing from the network. Findings are grouped into people, organisations, places, and numbers and contacts. For each value you choose hide or keep, a name can go to the brand list with one click, and anything the detectors missed is added in a field at the top. Press Done and the decisions go to `review.csv`. `--no-browser` prints the URL without opening it.

Two other ways to review, if you prefer them:

- `anon review` walks the list in the terminal: Enter hides a value, `n` marks a false hit, then you type anything that was missed. `anon review --add "Санек" --kind PERSON` adds one value directly.
- `review.csv` opens in Excel or Numbers: put `no` in the `keep` column for false hits, add rows for anything missed.

Decisions are stored in the vault and applied to every next file of the project. `anon list` prints the review list as a table.

**Apply and restore.** `anon apply` refuses to write a file if any known real value is still in it, and lists what is left and where. `anon restore` writes the real values back into the model's answer and lists every label the model bent (`[ИМЯ_1]-ой`, `PERSON_1` without brackets) or invented.

The vault password is asked once per command; for scripts, set `ANON_PASSWORD`. Messages follow the system locale, Russian or English; `ANON_LANG=ru` or `ANON_LANG=en` overrides it.

## Walk through it in 20 minutes

The whole cycle on invented data from this repository. Run the commands in a plain terminal window, not through an agent.

**1. Install and create a practice folder.** Install as described above. Then:

```sh
mkdir ~/anon-practice && cd ~/anon-practice
R=https://raw.githubusercontent.com/vasilievyakov/interview-anonymizer/main/tests/fixtures
curl -LO $R/live/corpus/03_pulsplan_en.md
curl -LO $R/live/corpus/01_pulsplan_oleg.md
curl -LO $R/en/staff.xlsx
```

One English interview, one Russian interview and a staff table. Open the interviews and look at what is in them: names, phones, employers, brands.

**2. Keep list.**

```sh
anon keep PulsePlan ПульсПлан Ritmo Ритмо FitBox
```

The answer is "Added to the list: 5" and the list itself. These names stay in the text.

**3. Scan.**

```sh
anon scan 03_pulsplan_en.md 01_pulsplan_oleg.md staff.xlsx
```

The first run takes 10 to 25 seconds. It ends with the number of values found in 3 files, a line on how many matched the keep list, and a hint about the next step. `review.csv` appears in the folder.

**4. What an agent sees.**

```sh
CLAUDECODE=1 anon list
CLAUDECODE=1 anon review
```

The first command prints only counts per kind, no values. The second refuses to run and asks a person to review in their own window.

**5. Review.**

```sh
anon review --web
```

A local page opens in the browser. Go through the groups and press "hide" or "keep". Two places to try: the word "Format" from the file header is listed as a person, so keep it; the observer Inna Kravets in the header is not in the list at all, so add her name in the top field. Send one brand to the keep list with its button. Press "Done". The terminal reports how many values are hidden, skipped and added by hand.

**6. Apply.**

```sh
anon apply
```

There is no vault yet, so `apply` asks you to choose a password and repeat it. Without it the labels cannot be restored. It ends with "Done. Leak check passed". If it says STOPPED, a value you chose to hide is still in the text: add it on the review page (step 5) and run `anon apply` again. After a successful `apply`, `review.csv` is deleted: the decisions are already in the encrypted vault.

**7. See what goes to the model.**

```sh
open 03_pulsplan_en.anon.md      # Linux: xdg-open
open staff.anon.xlsx
```

Names are replaced with `[PERSON_1]`, `[PERSON_2]`, the brands on the keep list are still there. In the table, names and contacts are replaced, numbers and formulas are the same.

**8. The model's answer.** Give `03_pulsplan_en.anon.md` to any model and save its answer as `answer.md`. Or write one yourself:

```sh
echo 'Summary: [PERSON_3] wants an offline mode. Call PERSON_2 next week.' > answer.md
```

**9. Restore.**

```sh
anon restore answer.md
cat answer.restored.md
```

After the password, `answer.restored.md` has the real names. `restore` lists `PERSON_2` separately: the model dropped the brackets, and that place needs a look.

**10. Optional: the skill and the hook.**

```sh
anon install-skill
```

Paste the printed snippet into `~/anon-practice/.claude/settings.json` and start Claude Code in that folder. Ask it to read `03_pulsplan_en.md`: the hook blocks it. Ask it to analyze the interviews: the agent follows the skill and hands the review to you.

Clean up: `uv tool uninstall interview-anonymizer` and the `~/anon-practice` folder.

## With Claude Code or Codex

An agent sees everything it reads and everything a command prints, and all of it goes to the cloud model. If the agent opens the source interview "to check one line", the names have left your machine before `anon` replaced anything. So the agent works only with `*.anon.*` files, and the review is done by a person, outside the agent.

**Quiet mode.** When `anon` runs under Claude Code or Codex, or its output does not go to a terminal, no command prints a value from the data. Scan reports files by number ("file 2 of 5"), since a file name can carry a respondent's name. `anon list` prints counts per kind. A blocked `apply` prints line numbers and kinds without the values. `restore` gives the number of places to check by hand and their lines. `anon review` in the terminal refuses to run and tells the person to review in their own window. A person who pipes the output on purpose can set `ANON_SHOW_VALUES=1` to see values again.

**Skill and hook for Claude Code.** `anon` ships a skill (`src/anon/claude/SKILL.md`) that walks the agent through keep, scan, a review by the person, apply, the work itself and restore, and a guard hook (`src/anon/claude/guard.py`). To install both:

```sh
anon install-skill
```

The command copies the skill and the hook to `~/.claude/skills/anonymize` and prints a snippet for `<project>/.claude/settings.json`. The hook runs on the Python that came with `anon`, so it works on a machine without a system Python. The command edits no settings; add the snippet to each project that holds data.

The hook blocks Read, Grep, Glob, Edit, Write and shell readers (`cat`, `head`, `grep`, `rg`, `sed`, `awk`, `python`, `cp`, `open` and similar) when they touch:

- the files listed in the last scan of the project;
- an original whose anonymized twin lies next to it (`interview.md` when `interview.anon.md` exists);
- `review.csv`, anything under `.anon/`, any `*.restored.*` file, and folders holding them.

It also blocks any command that sets `ANON_SHOW_VALUES`. The block message never quotes a path, because file names can carry names.

Known limits:

- The hook reads the scan state from the agent's working folder. Files of a project passed with `--project` elsewhere are protected only after `anon apply`, through the twin rule.
- The local review page is not intercepted by the hook. If the agent fetched its URL, it would see the values; only the skill forbids that.
- The hook is a seatbelt against honest mistakes. It covers the tools listed above and is no sandbox against an agent determined to get around it.

**Codex.** Quiet mode works in Codex the same way. The hook is Claude Code only. `SKILL.md` follows the common skill format; to use it in Codex, run `CLAUDE_SKILLS_DIR=<folder your Codex reads skills from> anon install-skill`.

## How it finds personal data

Three independent layers. A value is flagged if any of them finds it.

| Layer | Finds | Languages |
|---|---|---|
| Rules | phones, emails, SNILS, INN, passport numbers, bank cards, SSN, UK National Insurance numbers. Checksums are verified, so amounts, dates and timestamps are not flagged | ru, en |
| [Natasha](https://github.com/natasha/natasha) | names, organisations, places; brings Russian names in any case to one form | ru |
| [spaCy](https://spacy.io) | names, organisations, places, as a second opinion | ru, en |

On top of them sit filters for transcript noise: speaker tags and timestamps, filler words, capitalised phrase starts, roles like "Интервьюер", generic abbreviations (HR, ИП, МФЦ). Then a person reviews the merged list. The review is part of the design: automatic detection misses things (see below).

## Why it is safe

- **Nothing leaves the machine before anonymization.** Detection and replacement are local. A test (`tests/test_offline.py`) runs the whole scan, apply and restore path with every network call blocked.
- **The leak check blocks the output.** After replacement, the output is searched for every real value the vault knows and every value you chose to hide. If anything is left, the file is not written.
- **The vault is encrypted.** `.anon/vault.bin` maps labels back to real values. It is encrypted with your password (scrypt and Fernet); without the password it is opaque bytes. Do not share it and do not commit it (it is in `.gitignore`).
- **Restore shows what it is unsure of.** If the model bent a label or invented a new one, restore replaces what it can and lists every such place.

## How it was made

The first version was built against a clean synthetic set: invented interviews and staff tables in Russian and English, every personal value marked by hand (`tests/fixtures/golden.json`). On the Russian interview it found all 98 marked values.

Then it met the first real research interviews and drowned. The review list ran to hundreds of rows. Speaker tags were glued to names, so "Олег (Speaker A)" became a person of its own. Speech-to-text started every phrase with a capital letter, and the NER layers took those words for names. The brands the research was about came in dozens of distorted spellings, each one a separate row. One respondent turned up under a full name, a diminutive and a lone surname, and got several labels.

The tool never sends data anywhere. Tuning it was a separate decision: the owner of the interviews allowed the coding agent and its subagents, which run on a cloud model, to read them. The values never went into the repository, the tests or the commit history; the history was checked against the reference set before every push.

Real interviews cannot go into a repository, so the work started with a way to measure:

1. **A reference set.** Interviews were labelled by subagents mention by mention, and every mention got a tier: *direct* (private persons, contacts), *quasi* (employers, small towns, districts, metro stations), *public* (the researched brands, big public chains, big cities, countries).
2. **A bench that prints numbers only.** `scripts/bench.py` runs scan, review and apply as one project and reports review rows by class, the share of direct and quasi mentions hidden, false labels and people split across labels. Its output carries no values from the data, so it can be shared. `--show` prints values and is meant for synthetic data.
3. **Fixes measured one by one.** Transcript noise filters, markdown tables, Russian word forms, joining name parts into one person, the keep list with distortion matching, cutting person spans at the right word. Each change was checked against the bench before the next one.
4. **A second synthetic set.** `tests/fixtures/live` reproduces the same difficulties with invented people, employers and brands: glued speaker tags, raw speech-to-text, distorted brand names, product names that read like personal names, one person under several forms. Anyone can rerun the before and after on it. Details in [tests/fixtures/live/README.md](tests/fixtures/live/README.md).

The same pass added the review page (with hundreds of findings, the terminal walk-through and the spreadsheet are where people give up), quiet mode, the skill and the hook.

## Measured on synthetic data

### Clean set

`uv run python scripts/eval.py` runs every layer on the invented interviews and tables of `tests/fixtures/ru` and `tests/fixtures/en`. Leaks and splits are counted after replacement with a fresh vault, with no human review.

Values found in the interviews, by layer:

| Layer | Russian interview | English interview |
|---|---|---|
| Rules | 12 of 98 | 12 of 98 |
| Natasha | 84 of 98 | 0 of 98 (Russian only) |
| spaCy | 81 of 98 | 79 of 98 |
| All layers | **98 of 98** | **91 of 98** |

| File | False hits | Leaks after replace | Entities under several labels |
|---|---|---|---|
| Russian interview | 1 | 0 | 9 of 35 |
| English interview | 8 | 1 | 6 of 39 |
| Russian staff table | | 0 | 1 of 125 |
| English staff table | | 0 | 4 of 166 |

The seven values missed in the English interview are nicknames and lone surnames ("Robbo", "Fairbairn", "Em's"). In both tables none of the 40 formulas changed, and no number or header changed. The tuning for real speech did not cost anything here: at the commit before it, false hits were 9 and 19, and leaks 3.

### Live-like set, before and after

`scripts/bench.py` on `tests/fixtures/live`: seven files, 575 direct and 94 quasi mentions, 56 people. "Before" is the first version of 2026-10-01, before tuning on real interviews, with the same bench adapted to it; the keep list did not exist then. "Now" is the current version. The hidden share and the labels assume the person hides every flagged row and adds nothing by hand.

| | Before | Now | Now, with keep list |
|---|---|---|---|
| Review rows | 682 | 220 | 220, of them 41 already decided |
| of them names and contacts | 152 | 96 | 96 |
| of them employers and places | 49 | 42 | 42 |
| of them public brands and big cities | 136 | 66 | 66 |
| of them nothing personal | 345 | 16 | 16 |
| Names and contacts hidden | 98.1% | 98.4% | 98.4% |
| Employers and places hidden | 87.2% | 85.1% | 85.1% |
| False labels (nothing personal) | 898 of 2075, 43.3% | 32 of 1173, 2.7% | 32 of 780, 4.1% |
| Labels on public names | 536, 25.8% | 494, 42.1% | 101, 12.9% |
| People under several labels | 39 of 56 | 20 of 56 | 20 of 56 |

Names are found as well as before. What changed is the work left to the person: three times fewer rows to read, junk down from half of the list to 7%, the same people split into fewer labels. Employers and places are hidden slightly less often, 85.1% against 87.2%: that is the price of stricter filtering of speech-to-text without punctuation, and these are exactly the gaps the review closes. The keep list removes most public names from the output, so the model still sees the brands it is asked about. The share of false labels grows with the keep list only because there are fewer labels in total.

These numbers come from synthetic text. Real speech is messier, so expect more misses and more junk on your data. The values left in the text are what the review is for: the person adds them on the page, and the leak check holds them back in every next file.

## What it does not catch

- **Indirect identifiers.** "The only accountant in our Tver branch" names no one but identifies a person. Only the review catches this.
- **Lowercase speech-to-text.** Both NER layers rely on capital letters. In a fully lowercase transcript most names are missed. An employer whose name is made of ordinary words and is written in lowercase ("работаю в вектор сервис") stays in the text: a lowercase dictionary word is treated as speech, even when the same name was found elsewhere with capitals.
- **Rare nicknames and unfamiliar names.** Diminutives like "Ванюша", short forms like "Soph", and names from other languages inside an English interview are often missed.
- **Small places.** Some districts, streets and metro stations are missed, especially in oblique cases or when they look like an adjective or a product name.
- **Interview ids, by design.** Codes like `Инт.12_Hs5nJd` stay in the text, so the model can cite a respondent. They are pseudonyms; anyone holding the study's register can link them back. If that register is sensitive, add the codes in the review.
- **Phones without a country code** ("912 345-67-89") and unusual number formats.
- **Rare numbers.** The highest salary in a small team can identify a person even without a name. Numbers are kept as they are on purpose.
- **Model grammar.** Labels do not decline. Restore writes names in the nominative case, so "with [ИМЯ_1]" comes back as "with Мария Ковалева". Restore lists the places where the model attached a case ending.

## For developers

```sh
git clone https://github.com/vasilievyakov/interview-anonymizer
cd interview-anonymizer
uv sync
uv run pytest                 # all tests
uv run pytest -m "not models" # without loading the language models
uv run python scripts/make_fixtures.py   # rebuild the clean synthetic set
uv run python scripts/eval.py            # recall per layer, leaks
uv run python scripts/bench.py --dir tests/fixtures/live --keep tests/fixtures/live/keep.txt
```

Module map: [CONTRACTS.md](CONTRACTS.md).

## License

MIT.
