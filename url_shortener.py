"""A persistent URL shortener served entirely by Python's standard library."""
from __future__ import annotations

import argparse
import html
import json
import re
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{6,32}$")


def validate_url(url: str) -> str:
    """Accept absolute HTTP(S) URLs with a host; reject control/header injection."""
    value = url.strip()
    if not value or len(value) > 4096 or any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        raise ValueError("Enter a valid HTTP or HTTPS URL (up to 4096 characters).")
    try:
        parts = urlsplit(value)
        hostname = parts.hostname
        _ = parts.port
    except ValueError as exc:
        raise ValueError("Enter a valid HTTP or HTTPS URL.") from exc
    if parts.scheme.lower() not in {"http", "https"} or not hostname or " " in hostname:
        raise ValueError("Only absolute HTTP and HTTPS URLs with a hostname are supported.")
    if parts.username is not None or parts.password is not None:
        raise ValueError("URLs containing embedded credentials are not accepted.")
    return value


class ShortenerStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._lock = threading.Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self._save({})

    def _load(self) -> dict[str, str]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"Could not read URL database {self.path}: {exc}") from exc
        if not isinstance(data, dict) or not all(
            isinstance(key, str) and isinstance(value, str) for key, value in data.items()
        ):
            raise RuntimeError(f"URL database has invalid contents: {self.path}")
        return data

    def _save(self, data: dict[str, str]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        pending = self.path.with_name(self.path.name + ".tmp")
        pending.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
        pending.replace(self.path)

    def add(self, url: str) -> str:
        target = validate_url(url)
        with self._lock:
            data = self._load()
            short_id = secrets.token_urlsafe(6)
            while short_id in data:
                short_id = secrets.token_urlsafe(6)
            data[short_id] = target
            self._save(data)
        return short_id

    def get(self, short_id: str) -> str | None:
        if not ID_PATTERN.fullmatch(short_id):
            return None
        with self._lock:
            return self._load().get(short_id)

    def count(self) -> int:
        with self._lock:
            return len(self._load())


def make_handler(store: ShortenerStore, base_url: str):
    class Handler(BaseHTTPRequestHandler):
        def _send(self, status: int, body: str, content_type: str = "text/html; charset=utf-8"):
            encoded = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def do_GET(self):
            short_id = self.path.split("?", 1)[0].lstrip("/")
            if not short_id:
                body = (
                    "<!doctype html><title>Local URL Shortener</title>"
                    "<h1>Local URL Shortener</h1>"
                    "<form method='post' action='/shorten'>"
                    "<label>URL <input name='url' type='url' required maxlength='4096'></label> "
                    "<button type='submit'>Shorten</button></form>"
                    f"<p>{store.count()} saved link(s)</p>"
                )
                return self._send(200, body)
            target = store.get(short_id)
            if target is None:
                return self._send(404, "<!doctype html><h1>Short link not found</h1>")
            self.send_response(302)
            self.send_header("Location", target)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def do_POST(self):
            if self.path != "/shorten":
                return self._send(404, "<!doctype html><h1>Not found</h1>")
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if size < 1 or size > 8192:
                    raise ValueError("Submit one URL (maximum request size is 8192 bytes).")
                fields = parse_qs(self.rfile.read(size).decode("utf-8"), max_num_fields=10)
                short_id = store.add(fields.get("url", [""])[0])
            except (ValueError, UnicodeDecodeError) as exc:
                return self._send(400, f"<!doctype html><h1>Invalid URL</h1><p>{html.escape(str(exc))}</p>")
            short_url = html.escape(f"{base_url.rstrip('/')}/{short_id}", quote=True)
            self._send(201, f"<!doctype html><h1>Short URL created</h1><p><a href='{short_url}'>{short_url}</a></p>")

        def log_message(self, format, *args):
            print(f"[{self.log_date_time_string()}] {format % args}")

    return Handler


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1", help="Bind address (default: localhost only)")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--database", type=Path, default=Path.home() / ".url-shortener" / "urls.json")
    args = parser.parse_args(argv)
    store = ShortenerStore(args.database)
    base_url = f"http://{args.host}:{args.port}"
    server = ThreadingHTTPServer((args.host, args.port), make_handler(store, base_url))
    print(f"URL shortener ready at {base_url} (database: {args.database})")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())