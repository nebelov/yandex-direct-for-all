from __future__ import annotations

import http.server
import json
import sys
import threading
import unittest
import urllib.parse
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import portable_http  # noqa: E402


class Handler(http.server.BaseHTTPRequestHandler):
    def reply(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/redirect":
            self.send_response(302)
            self.send_header("Location", "/ok?redirected=1")
            self.end_headers()
            return
        self.reply(200, {"query": urllib.parse.parse_qs(parsed.query), "header": self.headers.get("X-Test")})

    def do_POST(self) -> None:
        size = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(size).decode("utf-8")
        if self.path == "/error":
            self.reply(409, {"error": "conflict"})
            return
        self.reply(200, {"content_type": self.headers.get("Content-Type"), "body": body})

    def log_message(self, _format: str, *_args: object) -> None:
        return


class PortableHttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def test_get_params_session_headers_and_redirect(self) -> None:
        session = portable_http.Session()
        session.headers.update({"X-Test": "shared"})
        response = session.get(f"{self.base}/ok", params={"value": ["a", "b"]}, allow_redirects=True)
        self.assertTrue(response.ok)
        self.assertEqual(response.json(), {"query": {"value": ["a", "b"]}, "header": "shared"})
        self.assertEqual(portable_http.get(f"{self.base}/redirect").json()["query"], {"redirected": ["1"]})

    def test_json_form_http_error_and_context_manager(self) -> None:
        json_response = portable_http.post(f"{self.base}/ok", json={"value": "пример"})
        self.assertIn("application/json", json_response.json()["content_type"])
        self.assertEqual(json.loads(json_response.json()["body"]), {"value": "пример"})
        form_response = portable_http.post(f"{self.base}/ok", data={"code": "a b"}, timeout=(1, None))
        self.assertEqual(form_response.json()["body"], "code=a+b")
        with portable_http.post(f"{self.base}/error", json={}) as error_response:
            self.assertFalse(error_response.ok)
            with self.assertRaises(portable_http.HTTPStatusError):
                error_response.raise_for_status()


if __name__ == "__main__":
    unittest.main()
