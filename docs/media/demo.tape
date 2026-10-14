# Interview anonymizer: terminal demo on the synthetic files.
# Rebuild from the repository root: vhs docs/media/demo.tape
Output docs/media/demo.gif

Set Shell "bash"
Set FontSize 20
Set Width 1400
Set Height 780
Set Padding 28
Set Theme "Builtin Dark"
Set TypingSpeed 30ms

Hide
Type `R=$PWD; W=$(mktemp -d); cp tests/fixtures/live/corpus/01_pulsplan_oleg.md tests/fixtures/live/corpus/04_grocery_svetlana.md tests/fixtures/ru/staff.xlsx $W; cd $W; anon() { uv run -q --project "$R" anon "$@"; }; export ANON_PASSWORD=demo ANON_LANG=ru ANON_SHOW_VALUES=1 PS1='$ '; anon --version >/dev/null; clear`
Enter
Sleep 3s
Show

Type "# interview-anonymizer: интервью и таблицы перед облачной моделью"
Enter
Sleep 1s
Type "anon keep ПульсПлан Ритмо FitBox Корзинка"
Enter
Sleep 2s
Type "anon scan 01_pulsplan_oleg.md 04_grocery_svetlana.md staff.xlsx"
Enter
Hide
Sleep 15s
Show
Sleep 4s

Hide
Type `anon review --web --no-browser > w.log 2>&1 & sleep 4; U=$(grep -o 'http://127[^ ]*' w.log | head -1); curl -s -X POST "${U%%/?t=*}/api/done?t=${U##*t=}" >/dev/null; wait; rm -f w.log; clear`
Enter
Sleep 6s
Show

Type "# человек прошел проверку на локальной странице: anon review --web"
Enter
Sleep 1s
Type "anon apply"
Enter
Hide
Sleep 15s
Show
Sleep 3s
Type "sed -n 5,9p 01_pulsplan_oleg.md"
Enter
Sleep 2s
Type "sed -n 5,9p 01_pulsplan_oleg.anon.md"
Enter
Sleep 5s

Hide
Type "clear"
Enter
Sleep 1s
Show

Type "# ответ модели приходит с метками"
Enter
Type "echo 'Итог: [ИМЯ_1] хочет офлайн-режим, интервью вела [ИМЯ_2].' > answer.md"
Enter
Sleep 1s
Type "anon restore answer.md"
Enter
Hide
Sleep 12s
Show
Sleep 1s
Type "cat answer.restored.md"
Enter
Sleep 5s
