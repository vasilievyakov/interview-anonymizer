"""User-facing messages in Russian and English.

Language: ANON_LANG (ru/en), else the system locale (LANG, LC_ALL), else English.
"""

from __future__ import annotations

import os

MESSAGES: dict[str, dict[str, str]] = {
    "password_prompt": {
        "ru": "Пароль словаря: ",
        "en": "Vault password: ",
    },
    "password_new": {
        "ru": "Словаря еще нет. Придумайте пароль, без него метки не расшифровать: ",
        "en": "No vault yet. Choose a password, labels cannot be restored without it: ",
    },
    "password_repeat": {
        "ru": "Повторите пароль: ",
        "en": "Repeat the password: ",
    },
    "password_mismatch": {
        "ru": "Пароли не совпали.",
        "en": "Passwords do not match.",
    },
    "wrong_password": {
        "ru": "Неверный пароль словаря.",
        "en": "Wrong vault password.",
    },
    "file_missing": {
        "ru": "Файл не найден: {path}",
        "en": "File not found: {path}",
    },
    "unsupported": {
        "ru": "Формат не поддерживается: {path}. Подходят xlsx, csv, md, txt, docx.",
        "en": "Unsupported format: {path}. Use xlsx, csv, md, txt or docx.",
    },
    "scanning": {
        "ru": "Ищу в {path} ({lang})...",
        "en": "Scanning {path} ({lang})...",
    },
    "name_in_filename": {
        "ru": "ВНИМАНИЕ: в названии файла {path} похоже есть {kinds}. Название уйдет в модель вместе с файлом. Переименуйте его, например в interview-01{ext}.",
        "en": "WARNING: the file name {path} seems to contain {kinds}. The name goes to the model with the file. Rename it, e.g. to interview-01{ext}.",
    },
    "scan_done": {
        "ru": "Найдено значений: {n}, файлов: {files}. Список на проверку: {review}",
        "en": "Found {n} values in {files} files. Review list: {review}",
    },
    "scan_next": {
        "ru": "Дальше: anon review --web откроет страницу проверки (или откройте {review} и поставьте 'нет' в колонке keep у лишнего), затем anon apply.",
        "en": "Next: anon review --web opens the review page (or open {review} and put 'no' in the keep column for false hits), then anon apply.",
    },
    "scan_kept_public": {
        "ru": "Совпало со списком публичных названий (anon keep, города, страны): {n}. Они останутся в тексте, в review.csv у них keep = no.",
        "en": "{n} of them match the public names list (anon keep, cities, countries) and stay in the text; keep = no in review.csv.",
    },
    "skill_installed": {
        "ru": "Скилл и хук установлены: {dest}",
        "en": "Skill and hook installed: {dest}",
    },
    "skill_snippet": {
        "ru": "Чтобы закрыть агенту исходные данные проекта, добавьте это в <проект>/.claude/settings.json (если там уже есть \"hooks\", объедините):",
        "en": "To keep the agent away from a project's original data, add this to <project>/.claude/settings.json (merge with existing \"hooks\" if there are any):",
    },
    "keep_added": {
        "ru": "Добавлено в список: {n}.",
        "en": "Added to the list: {n}.",
    },
    "keep_list": {
        "ru": "Публичных названий проекта: {n}. Они остаются в тексте во всех формах, города-миллионники и страны остаются всегда:",
        "en": "Public names of this project ({n}), kept in the text in every form. Cities over a million and countries are always kept:",
    },
    "review_skipped": {
        "ru": "{n} значений уже решены (список anon keep или прошлые проверки), их не спрашиваю. Поправить можно в review.csv.",
        "en": "{n} values are already decided (anon keep list or earlier reviews) and are not asked. Change them in review.csv.",
    },
    "no_scan": {
        "ru": "Сначала запустите anon scan.",
        "en": "Run anon scan first.",
    },
    "review_header": {
        "ru": "Проверка: Enter — скрыть, n — это не личное, q — закончить проверку.",
        "en": "Review: Enter hides it, n means not sensitive, q finishes the review.",
    },
    "review_item": {
        "ru": "[{i}/{total}] {kind}: {text}  (встречается {count} раз, слои: {sources})\n    ...{context}...",
        "en": "[{i}/{total}] {kind}: {text}  (seen {count} times, layers: {sources})\n    ...{context}...",
    },
    "review_add": {
        "ru": "Что еще скрыть? Введите текст как в файле (пусто — закончить): ",
        "en": "Anything else to hide? Type it as in the file (empty to finish): ",
    },
    "review_add_kind": {
        "ru": "Тип: 1 — имя, 2 — организация, 3 — место, 4 — другое [1]: ",
        "en": "Kind: 1 person, 2 organisation, 3 place, 4 other [1]: ",
    },
    "review_done": {
        "ru": "Скрываем {keep}, пропускаем {skip}, добавлено вручную {added}.",
        "en": "Hiding {keep}, skipping {skip}, added by hand {added}.",
    },
    "review_web_url": {
        "ru": "Проверка в браузере: {url}",
        "en": "Review in the browser: {url}",
    },
    "review_web_wait": {
        "ru": "Жду, пока на странице нажмут «Готово». Ctrl+C — выйти без сохранения.",
        "en": 'Waiting for "Done" on the page. Ctrl+C quits without saving.',
    },
    "review_web_aborted": {
        "ru": "Проверка прервана, review.csv не изменен. Добавленное в список брендов осталось в нем.",
        "en": "Review interrupted, review.csv is unchanged. Names added to the brand list stay there.",
    },
    "apply_file": {
        "ru": "{src} -> {dst}: заменено {n}",
        "en": "{src} -> {dst}: replaced {n}",
    },
    "file_n": {
        "ru": "файл {i} из {total}",
        "en": "file {i} of {total}",
    },
    "apply_file_quiet": {
        "ru": "{src} -> *{ext}: заменено {n}",
        "en": "{src} -> *{ext}: replaced {n}",
    },
    "leak_found": {
        "ru": "ОСТАНОВЛЕНО: в {path} осталось {n} настоящих значений. Файл не записан.",
        "en": "STOPPED: {path} still contains {n} real values. File not written.",
    },
    "leak_line": {
        "ru": "    строка {line}: {value}  ...{context}...",
        "en": "    line {line}: {value}  ...{context}...",
    },
    "leak_hint": {
        "ru": "Добавьте их через anon review или поставьте keep=yes в {review}, затем снова anon apply.",
        "en": "Add them with anon review or set keep=yes in {review}, then run anon apply again.",
    },
    "apply_done": {
        "ru": "Готово. Контроль утечек пройден. В модель можно отдавать файлы *.anon.*. Словарь: {vault}",
        "en": "Done. Leak check passed. Files *.anon.* are safe to send to the model. Vault: {vault}",
    },
    "restore_done": {
        "ru": "Расшифровано: {dst} (меток заменено: {n})",
        "en": "Restored: {dst} (labels replaced: {n})",
    },
    "restore_problems": {
        "ru": "Проверьте вручную ({n}):",
        "en": "Check by hand ({n}):",
    },
    "restore_unknown": {
        "ru": "строка {line}: {whole}, неизвестная метка",
        "en": "line {line}: {whole} unknown label",
    },
    "restore_read_as": {
        "ru": "строка {line}: {whole} прочитано как {label} -> {value} ({reasons})",
        "en": "line {line}: {whole} read as {label} -> {value} ({reasons})",
    },
    "restore_wrong_case": {"ru": "изменен регистр", "en": "wrong case"},
    "restore_missing_brackets": {"ru": "нет скобок", "en": "missing brackets"},
    "restore_space_sep": {"ru": "пробел вместо подчеркивания", "en": "space instead of underscore"},
    "restore_extra_spaces": {"ru": "лишние пробелы", "en": "extra spaces"},
    "restore_leading_zeros": {"ru": "ведущие нули", "en": "leading zeros"},
    "restore_case_ending": {
        "ru": "падежное окончание '{ending}' отброшено, проверьте грамматику",
        "en": "case ending '{ending}' dropped, check grammar",
    },
    # ---- agent-safe output (anon.agent.quiet) -----------------------------
    "scanning_quiet": {
        "ru": "Ищу в файле {i} из {total} ({lang})...",
        "en": "Scanning file {i} of {total} ({lang})...",
    },
    "name_in_filename_quiet": {
        "ru": "ВНИМАНИЕ: в названии файла {i} из {total}, похоже, есть {kinds}. Название уйдет в модель вместе с файлом. Переименуйте его, например в interview-01{ext}.",
        "en": "WARNING: the name of file {i} of {total} seems to contain {kinds}. The name goes to the model with the file. Rename it, e.g. to interview-01{ext}.",
    },
    "scan_next_quiet": {
        "ru": "Дальше проверку делает человек, а не агент: в своем окне терминала, вне агента, anon review --web (страница в браузере) или правка {review} в таблице. Вывод проверки не должен попадать к агенту. Затем anon apply.",
        "en": "Next, a person does the review, not the agent: in their own terminal window, outside the agent, anon review --web (a page in the browser) or edit {review} in a spreadsheet. The review output must not reach the agent. Then anon apply.",
    },
    "values_hidden": {
        "ru": "Значения не показываю: команду запустил агент или вывод не идет в терминал. Посмотреть их человек может сам: anon review --web или {review}.",
        "en": "Values are not shown: an agent runs this command or the output does not go to a terminal. A person can look at them: anon review --web or {review}.",
    },
    "list_kind_quiet": {
        "ru": "  {kind:<9} всего {n}, скрываем {keep}, оставляем в тексте {skip}",
        "en": "  {kind:<9} total {n}, hiding {keep}, leaving in the text {skip}",
    },
    "leak_lines_quiet": {
        "ru": "    строки: {lines}; типы: {kinds}",
        "en": "    lines: {lines}; kinds: {kinds}",
    },
    "leak_hint_quiet": {
        "ru": "Значения не показаны, и агенту их смотреть нельзя. Человек сам открывает anon review --web или {review} в своем окне терминала, добавляет пропущенное, затем снова anon apply.",
        "en": "Values are not shown, and the agent must not look at them. A person opens anon review --web or {review} in their own terminal window, adds what was missed, then runs anon apply again.",
    },
    "restore_problems_quiet": {
        "ru": "Проверьте вручную мест: {n}, строки: {lines}. Текст не показываю, откройте {dst} сами.",
        "en": "Check by hand: {n} places, lines {lines}. The text is not shown; open {dst} yourself.",
    },
    "review_quiet_refused": {
        "ru": "anon review в терминале показывает настоящие значения, а вывод этой команды сейчас уходит к агенту и в модель. Проверку делает человек: anon review --web в своем окне терминала, вне агента, или правка review.csv в таблице. Вывод проверки не должен попадать к агенту.",
        "en": "anon review in the terminal shows the real values, and the output of this command now goes to the agent and the model. A person does the review: anon review --web in their own terminal window, outside the agent, or edit review.csv in a spreadsheet. The review output must not reach the agent.",
    },
}


def lang() -> str:
    explicit = os.environ.get("ANON_LANG", "").lower()
    if explicit in ("ru", "en"):
        return explicit
    for var in ("LC_ALL", "LC_MESSAGES", "LANG"):
        value = os.environ.get(var, "")
        if value:
            return "ru" if value.lower().startswith("ru") else "en"
    return "en"


def t(key: str, **kwargs: object) -> str:
    return MESSAGES[key][lang()].format(**kwargs)
