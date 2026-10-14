"""Browser review: local server, token, decisions back into review.csv. No models needed."""

import json
import re
import threading
import urllib.error
import urllib.request

import pytest

from anon.keep import read_values
from anon.model import Kind
from anon.review import Item, read_csv, write_csv
from anon.webreview import WebReview, page, serve

ITEMS = [
    Item(
        kind=Kind.PERSON,
        text="Мария Ковалева",
        count=3,
        variants={"Мария Ковалева", "Ковалевой"},
        files={"interview-01.md"},
        sources={"natasha", "spacy"},
        context="вчера звонила Ковалевой по поводу отчета",
    ),
    Item(
        kind=Kind.ORG,
        text="ООО Северный ветер",
        count=2,
        variants={"ООО Северный ветер"},
        files={"interview-01.md"},
        sources={"natasha"},
        context="работаю в ООО Северный ветер третий год",
    ),
    Item(
        kind=Kind.PHONE,
        text="+7 912 345-67-89",
        count=1,
        variants={"+7 912 345-67-89"},
        files={"interview-01.md"},
        sources={"rules"},
        context="телефон +7 912 345-67-89",
    ),
    Item(
        kind=Kind.ORG,
        text="Ромашка Плюс",
        keep=False,
        count=1,
        variants={"Ромашка Плюс"},
        files={"interview-01.md"},
        sources={"natasha", "keep"},
        context="заказывали в Ромашка Плюс",
    ),
]


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("ANON_LANG", "ru")
    review = tmp_path / "review.csv"
    write_csv(ITEMS, review)
    web = WebReview(tmp_path, read_csv(review))
    web.start()
    yield web
    if not web.done.is_set():
        web.close()


def call(web, path, body=None, token=True):
    url = f"http://127.0.0.1:{web.port}{path}"
    if token:
        url += f"?t={web.token}"
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(
        url, data=data, method="GET" if data is None and path != "/api/done" else "POST"
    )
    if data is not None:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=5) as r:
        return r.status, r.headers, r.read()


def api(web, path, body=None):
    return json.loads(call(web, path, body)[2])


def by_text(items, text):
    return next(i for i in items if i["text"] == text)


def test_token_required(app):
    for path in ("/", "/api/items"):
        with pytest.raises(urllib.error.HTTPError) as e:
            call(app, path, token=False)
        assert e.value.code == 403
    with pytest.raises(urllib.error.HTTPError) as e:
        req = urllib.request.Request(
            f"http://127.0.0.1:{app.port}/api/keep?t=wrong",
            data=b'{"id": 0, "keep": false}',
            method="POST",
        )
        urllib.request.urlopen(req, timeout=5)
    assert e.value.code == 403
    # Nothing changed without the token.
    assert by_text(api(app, "/api/items")["items"], "Мария Ковалева")["keep"] is True


def test_page_headers_and_items(app):
    status, headers, body = call(app, "/")
    assert status == 200
    csp = headers["Content-Security-Policy"]
    assert "connect-src 'self'" in csp and "default-src 'none'" in csp
    assert "<script>" in body.decode()
    data = api(app, "/api/items")
    assert data["lang"] == "ru"
    assert len(data["items"]) == 4
    assert by_text(data["items"], "Ромашка Плюс")["decided"] is True
    assert by_text(data["items"], "Мария Ковалева")["decided"] is False


def test_bad_requests(app):
    for body in (
        {"id": 99, "keep": True},
        {"id": 0, "keep": "yes"},
        {"id": True, "keep": False},
    ):
        with pytest.raises(urllib.error.HTTPError) as e:
            call(app, "/api/keep", body)
        assert e.value.code == 400
    phone = by_text(api(app, "/api/items")["items"], "+7 912 345-67-89")["id"]
    with pytest.raises(urllib.error.HTTPError) as e:
        call(app, "/api/brand", {"id": phone})
    assert e.value.code == 400
    with pytest.raises(urllib.error.HTTPError) as e:
        call(app, "/api/add", {"text": "  ", "kind": "PERSON"})
    assert e.value.code == 400


def test_full_review_round(app, tmp_path):
    items = api(app, "/api/items")["items"]
    person = by_text(items, "Мария Ковалева")["id"]
    org = by_text(items, "ООО Северный ветер")["id"]
    decided = by_text(items, "Ромашка Плюс")["id"]

    assert api(app, "/api/keep", {"id": person, "keep": False})["item"]["keep"] is False
    assert api(app, "/api/keep", {"id": decided, "keep": True})["item"]["keep"] is True
    brand = api(app, "/api/brand", {"id": org})
    assert brand["added"] is True and brand["item"]["keep"] is False
    added = api(app, "/api/add", {"text": "Санек", "kind": "PERSON"})["item"]
    assert added["keep"] is True and added["sources"] == ["user"]

    counts = api(app, "/api/done")
    assert counts == {"hide": 3, "keep": 2, "total": 5, "added": 1}
    assert app.wait(5)
    app._thread.join(5)
    assert not app._thread.is_alive()
    with pytest.raises(OSError):
        call(app, "/api/items")

    saved = {i.text: i for i in read_csv(tmp_path / "review.csv")}
    assert set(saved) == {
        "Мария Ковалева",
        "ООО Северный ветер",
        "+7 912 345-67-89",
        "Ромашка Плюс",
        "Санек",
    }
    assert saved["Мария Ковалева"].keep is False
    assert saved["Мария Ковалева"].variants == {"Мария Ковалева", "Ковалевой"}
    assert saved["ООО Северный ветер"].keep is False
    assert "keep" in saved["ООО Северный ветер"].sources
    assert saved["Ромашка Плюс"].keep is True
    assert saved["+7 912 345-67-89"].keep is True
    assert saved["Санек"].keep is True and saved["Санек"].kind == Kind.PERSON
    assert saved["Санек"].sources == {"user"}
    assert read_values(tmp_path) == ["ООО Северный ветер"]
    assert (tmp_path / ".anon" / "keep.txt").read_text(
        encoding="utf-8"
    ) == "ООО Северный ветер\n"


def test_english_lang(tmp_path, monkeypatch):
    monkeypatch.setenv("ANON_LANG", "en")
    web = WebReview(tmp_path, [])
    web.start()
    try:
        assert api(web, "/api/items")["lang"] == "en"
    finally:
        web.close()


def test_serve_prints_only_url(tmp_path, monkeypatch):
    monkeypatch.setenv("ANON_LANG", "ru")
    write_csv(ITEMS, tmp_path / "review.csv")
    lines: list[str] = []
    started = threading.Event()

    def say(line: str) -> None:
        lines.append(line)
        started.set()

    out: list = []
    th = threading.Thread(
        target=lambda: out.append(
            serve(tmp_path, read_csv(tmp_path / "review.csv"), False, say)
        )
    )
    th.start()
    assert started.wait(5)
    url = re.search(r"http://127\.0\.0\.1:\d+/\?t=\S+", lines[0]).group(0)
    with urllib.request.urlopen(
        urllib.request.Request(url.replace("/?", "/api/done?"), method="POST"),
        timeout=5,
    ):
        pass
    th.join(5)
    assert not th.is_alive() and len(out[0]) == 4
    printed = "\n".join(lines)
    for item in ITEMS:
        assert item.text not in printed and item.context not in printed


def test_cli_web_flag(tmp_path, monkeypatch, capsys):
    from anon import webreview
    from anon.cli import main

    monkeypatch.setenv("ANON_LANG", "en")
    write_csv(ITEMS, tmp_path / "review.csv")

    def fake_serve(project, items, open_browser=True, say=print):
        assert open_browser is False
        items[0].keep = False
        return items

    monkeypatch.setattr(webreview, "serve", fake_serve)
    main(["--project", str(tmp_path), "review", "--web", "--no-browser"])
    out = capsys.readouterr().out
    assert "Hiding 2, skipping 2" in out
    assert not any(i.text in out for i in ITEMS)
    assert read_csv(tmp_path / "review.csv")[0].keep is False


def test_page_loads_nothing_from_network():
    html = page()
    assert not re.search(r"https?://", html)
    assert "<link" not in html and "@import" not in html and "src=" not in html
    assert "ё" not in html
