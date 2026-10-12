import json
import http.client
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path

from url_shortener import ShortenerStore, make_handler, validate_url


class UrlValidationTests(unittest.TestCase):
    def test_accepts_http_and_https(self):
        self.assertEqual(validate_url(" https://example.com/path "), "https://example.com/path")
        self.assertEqual(validate_url("http://localhost:8080"), "http://localhost:8080")

    def test_rejects_invalid_urls(self):
        for value in ("", "ftp://example.com", "//example.com", "https://", "https://user:pass@example.com", "https://example.com\r\nX: y"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_url(value)


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.database = Path(__file__).with_name(".url-store-test.json")
        self.database.unlink(missing_ok=True)

    def tearDown(self):
        self.database.unlink(missing_ok=True)
        self.database.with_name(self.database.name + ".tmp").unlink(missing_ok=True)

    def test_ids_are_persistent_and_resolve(self):
        store = ShortenerStore(self.database)
        short_id = store.add("https://example.com/a")
        reopened = ShortenerStore(self.database)
        self.assertEqual(reopened.get(short_id), "https://example.com/a")
        self.assertEqual(reopened.count(), 1)
        self.assertIsNone(reopened.get("bad/id"))
        self.assertEqual(json.loads(self.database.read_text(encoding="utf-8"))[short_id], "https://example.com/a")

    def test_http_short_link_returns_a_real_redirect(self):
        store = ShortenerStore(self.database)
        short_id = store.add("https://example.com/destination")
        server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(store, "http://127.0.0.1"))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
            connection.request("GET", f"/{short_id}")
            response = connection.getresponse()
            self.assertEqual(response.status, 302)
            self.assertEqual(response.getheader("Location"), "https://example.com/destination")
            response.read()
            connection.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


if __name__ == "__main__":
    unittest.main()