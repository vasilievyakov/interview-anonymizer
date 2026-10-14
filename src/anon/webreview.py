"""Review in the browser: `anon review --web`.

With hundreds of findings the terminal walk-through and review.csv in a
spreadsheet are where people give up. This serves one local page over the same
items: hide or keep each value, send brands to the keep list, add what the
detectors missed, press «Готово». Decisions go to review.csv via write_csv.

The server listens on 127.0.0.1 only, on a random free port, and every request
must carry a random token (`?t=...` or the X-Anon-Token header). The page is one
self-contained file shipped with the package: it loads nothing from the network.
"""

from __future__ import annotations

import json
import secrets
import threading
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from . import keep as keep_list
from .i18n import lang, t
from .model import Kind
from .review import REVIEW_FILE, Item, write_csv

PAGE = "webreview.html"
# Inline styles and scripts only, requests only back to this server.
CSP = (
    "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; "
    "connect-src 'self'; img-src 'self'; base-uri 'none'; form-action 'none'; "
    "frame-ancestors 'none'"
)
MAX_BODY = 64 * 1024
MAX_TEXT = 500
# The "в список брендов" button is offered for names, not for numbers and contacts.
BRAND_KINDS = (Kind.PERSON, Kind.ORG, Kind.LOCATION)
# Kinds a missed value can be added as, in the order the page shows them.
ADD_KINDS = (Kind.PERSON, Kind.ORG, Kind.LOCATION, Kind.PHONE, Kind.EMAIL, Kind.ID)


def page() -> str:
    return resources.files("anon").joinpath(PAGE).read_text(encoding="utf-8")


class BadRequest(ValueError):
    pass


class Session:
    """Items under review and what the page did to them. All access under one lock."""

    def __init__(self, project: Path, items: list[Item]) -> None:
        self.project = Path(project)
        self.items = items
        # Decided before the page opened (keep list, earlier reviews): shown collapsed.
        # Fixed at load, so a row does not jump between sections while being toggled.
        self.decided = [not i.keep for i in items]
        self.lock = threading.Lock()

    def _json(self, idx: int) -> dict:
        item = self.items[idx]
        return {
            "id": idx,
            "kind": item.kind.value,
            "text": item.text,
            "keep": item.keep,
            "count": item.count,
            "variants": sorted(item.variants),
            "files": sorted(item.files),
            "sources": sorted(item.sources),
            "context": item.context,
            "decided": self.decided[idx],
        }

    def _index(self, data: dict) -> int:
        idx = data.get("id")
        if (
            not isinstance(idx, int)
            or isinstance(idx, bool)
            or not 0 <= idx < len(self.items)
        ):
            raise BadRequest("id")
        return idx

    def snapshot(self) -> dict:
        with self.lock:
            return {
                "lang": lang(),
                "review": REVIEW_FILE,
                "brand_kinds": [k.value for k in BRAND_KINDS],
                "add_kinds": [k.value for k in ADD_KINDS],
                "items": [self._json(n) for n in range(len(self.items))],
            }

    def set_keep(self, data: dict) -> dict:
        if not isinstance(data.get("keep"), bool):
            raise BadRequest("keep")
        with self.lock:
            idx = self._index(data)
            self.items[idx].keep = data["keep"]
            return {"item": self._json(idx)}

    def to_brand(self, data: dict) -> dict:
        """Add the value to the project keep list; the row becomes "оставить"."""
        with self.lock:
            idx = self._index(data)
            item = self.items[idx]
            if item.kind not in BRAND_KINDS:
                raise BadRequest("kind")
            added = keep_list.add_values(self.project, [item.text])
            item.keep = False
            item.sources.add("keep")
            return {"item": self._json(idx), "added": bool(added)}

    def add(self, data: dict) -> dict:
        """A value the detectors missed, same as `anon review --add`."""
        text = data.get("text")
        if not isinstance(text, str) or not text.strip() or len(text) > MAX_TEXT:
            raise BadRequest("text")
        try:
            kind = Kind(str(data.get("kind") or "PERSON").upper())
        except ValueError:
            raise BadRequest("kind") from None
        text = " ".join(text.split())
        with self.lock:
            self.items.append(
                Item(kind=kind, text=text, keep=True, variants={text}, sources={"user"})
            )
            self.decided.append(False)
            return {"item": self._json(len(self.items) - 1)}

    def save(self) -> dict:
        with self.lock:
            write_csv(self.items, self.project / REVIEW_FILE)
            return counts(self.items)


def counts(items: list[Item]) -> dict:
    hide = sum(1 for i in items if i.keep)
    return {
        "hide": hide,
        "keep": len(items) - hide,
        "total": len(items),
        "added": sum(1 for i in items if "user" in i.sources),
    }


class _Handler(BaseHTTPRequestHandler):
    app: WebReview  # set on a per-server subclass
    server_version = "anon"
    sys_version = ""

    def log_message(self, format: str, *args: object) -> None:
        pass  # request lines carry the token; values never reach the terminal

    def _authorized(self) -> bool:
        port = self.app.port
        if self.headers.get("Host", "") not in (
            f"127.0.0.1:{port}",
            f"localhost:{port}",
        ):
            return False  # DNS rebinding: another site's name pointed at 127.0.0.1
        query = parse_qs(urlsplit(self.path).query)
        token = (query.get("t") or [""])[0] or self.headers.get("X-Anon-Token", "")
        return secrets.compare_digest(token.encode(), self.app.token.encode())

    def _send(self, status: HTTPStatus, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Content-Security-Policy", CSP)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: HTTPStatus, data: dict) -> None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self._send(status, body, "application/json; charset=utf-8")

    def _error(self, status: HTTPStatus) -> None:
        self._json(status, {"error": status.phrase})

    def do_GET(self) -> None:
        if not self._authorized():
            return self._error(HTTPStatus.FORBIDDEN)
        route = urlsplit(self.path).path
        if route == "/":
            return self._send(
                HTTPStatus.OK, page().encode("utf-8"), "text/html; charset=utf-8"
            )
        if route == "/api/items":
            return self._json(HTTPStatus.OK, self.app.session.snapshot())
        self._error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        if not self._authorized():
            return self._error(HTTPStatus.FORBIDDEN)
        actions = {
            "/api/keep": self.app.session.set_keep,
            "/api/brand": self.app.session.to_brand,
            "/api/add": self.app.session.add,
        }
        route = urlsplit(self.path).path
        if route == "/api/done":
            self._json(HTTPStatus.OK, self.app.session.save())
            return self.app.finish()
        if route not in actions:
            return self._error(HTTPStatus.NOT_FOUND)
        try:
            size = int(self.headers.get("Content-Length") or 0)
            if not 0 < size <= MAX_BODY:
                raise BadRequest("size")
            data = json.loads(self.rfile.read(size).decode("utf-8"))
            if not isinstance(data, dict):
                raise BadRequest("body")
            result = actions[route](data)
        except (BadRequest, ValueError):
            return self._error(HTTPStatus.BAD_REQUEST)
        self._json(HTTPStatus.OK, result)


class WebReview:
    """The local server. start() serves in a background thread; wait() blocks until «Готово»."""

    def __init__(self, project: Path, items: list[Item]) -> None:
        self.session = Session(project, items)
        self.token = secrets.token_urlsafe(24)
        handler = type("Handler", (_Handler,), {"app": self})
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.server.daemon_threads = True
        self.done = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def port(self) -> int:
        return self.server.server_address[1]

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}/?t={self.token}"

    def start(self) -> None:
        self._thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self._thread.start()

    def wait(self, timeout: float | None = None) -> bool:
        return self.done.wait(timeout)

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        if self._thread is not None:
            self._thread.join()
        self.done.set()

    def finish(self) -> None:
        """Called from a request thread: shut down from another one, serve_forever waits on it."""
        threading.Thread(target=self.close, daemon=True).start()


def serve(
    project: Path, items: list[Item], open_browser: bool = True, say=print
) -> list[Item]:
    """Run the page until «Готово». Prints only the URL and the waiting note, never a value."""
    app = WebReview(project, items)
    app.start()
    say(t("review_web_url", url=app.url))
    if open_browser:
        webbrowser.open(app.url)
    say(t("review_web_wait"))
    try:
        app.wait()
    except KeyboardInterrupt:
        app.close()
        raise SystemExit(t("review_web_aborted")) from None
    return app.session.items
