---
name: anonymize
description: Anonymize interview transcripts and tables with the local `anon` tool before the agent works with them, so personal data never enters the model's context; restore real values in the final answer. Use when the user wants to analyze interviews, transcripts, survey answers or staff tables that contain names, phones, emails or company names, or says "anonymize", "hide personal data", "PII", "before sending to the model", "обезличь", "анонимизируй", "скрой персональные данные", "убери ФИО и телефоны", "интервью с респондентами", "/anonymize".
---

# Anonymize before analysis

`anon` replaces personal data with labels (`[ИМЯ_1]`, `[PERSON_1]`) on the person's machine and keeps the real values in an encrypted vault (`.anon/`). You work only with the `*.anon.*` files it writes. Everything a command prints, and every file you read, goes into the cloud model's context, so the original data must never pass through you.

`anon` detects that it runs under an agent and prints only counts, kinds and line numbers. That protects the output; the rules below protect everything else.

Invoke it as `anon` if it is on PATH, otherwise `uv run --project <path to interview-anonymizer> anon`. Set `ANON_PASSWORD` only if the person gives you a password to use; otherwise the person types it when asked.

## Hard rules

1. Never Read, cat, head, tail, grep, rg, sed, awk, copy or open the source files, `review.csv`, anything under `.anon/`, or any `*.restored.*` file. Not to "check one line", not to debug, not partially.
2. Never print, quote or guess a real value. Do not ask the person to paste values into the chat.
3. Read only `*.anon.*` files and the person's own instructions.
4. If `anon apply` stops with leaks, do not look at them and do not try to fix the vault yourself. Hand the review back to the person (step 4).
5. Never run `anon review` without `--web`, never set `ANON_SHOW_VALUES`, never open or fetch the local review page.
6. Do not run the review through `!` either: in Claude Code the output of `! command` also reaches the model.
7. If something blocks a call (the anon guard hook), accept it. Do not look for a way around it.

## Steps

1. **Ask the person** which files to anonymize (paths only) and which public brands, products or services the study is about. Those stay in the text. Do not open the files to find out.

2. **Keep list.** Once per project:
   ```sh
   anon keep "Brand A" "Brand B"
   ```

3. **Scan.**
   ```sh
   anon scan interview-01.md interview-02.md staff.xlsx
   ```
   Only counts come back. If it warns that a file name contains a name, ask the person to rename the file (e.g. `interview-01.md`) and scan again.

4. **Review by the person, outside the agent.** Tell the person, in these words or close to them:
   > Open your own terminal window, not this chat, go to the project folder and run `anon review --web`. A local page opens in your browser: hide what is personal, leave false hits, add anything missed. You can also edit `review.csv` in Excel or Numbers instead. Do not paste anything from the review here. Tell me when you are done.

   Wait for the person to confirm. Then you may run `anon list`: it prints counts per kind, no values.

5. **Apply.**
   ```sh
   anon apply
   ```
   It replaces values, runs the leak check and writes `*.anon.*` next to each source. If it says STOPPED, report the file, line numbers and kinds it printed, and go back to step 4: the person adds the missed values in the review and you run `anon apply` again. Never inspect the lines yourself.

6. **Work.** Read the `*.anon.*` files and do the task. Keep labels exactly as they are (`[ИМЯ_1]`, not "Мария" or "[имя 1]"), so they can be restored. Write the result to a new file, e.g. `answer.md`.

7. **Restore.**
   ```sh
   anon restore answer.md
   ```
   It writes `answer.restored.md` with real values. Do not open it. If it reports places to check by hand, pass the count and line numbers to the person; they check the file themselves.

## Guard hook

`anon` ships a PreToolUse hook (`guard.py`) that blocks reads of originals, `review.csv`, `.anon/` and `*.restored.*`. If the person has not installed it, suggest `anon install-skill`, which installs this skill with the hook and prints the settings snippet for the project.
