"""A small HTTP workbench. Default: loopback, cached reads and no external calls."""

from __future__ import annotations

import hmac
import json
import mimetypes
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from .engine import ResearchEngine
from .notifications import email_preview
from .reports import digest_report


STATIC = Path(__file__).parent / "static"
MAX_BODY = 512 * 1024


def make_server(engine: ResearchEngine, host: str = "127.0.0.1", port: int = 8765,
                token: str | None = None, public_origin: str | None = None) -> ThreadingHTTPServer:
    if host not in {"127.0.0.1", "localhost"} and not token:
        raise ValueError("A non-loopback server requires THESISLEDGER_API_TOKEN and an authenticated TLS reverse proxy")
    if public_origin:
        origin_url = urlparse(public_origin)
        if not token or origin_url.scheme != "https" or not origin_url.hostname or origin_url.username or origin_url.password or origin_url.path or origin_url.query or origin_url.fragment:
            raise ValueError("A trusted public origin requires an API token and an exact HTTPS origin without a path")

    class Handler(BaseHTTPRequestHandler):
        server_version = "ThesisLedger"

        def log_message(self, *_args):
            # Do not persist request headers, query strings or user data.
            return

        def reply(self, payload: dict, code: int = 200) -> None:
            data = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(data)

        def allowed_host(self) -> bool:
            header = self.headers.get("Host", "")
            if host in {"127.0.0.1", "localhost"}:
                return header in {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}
            return bool(header) and "/" not in header

        def authenticated(self) -> bool:
            if not self.allowed_host():
                self.reply({"error": "host_rejected", "message": "Unexpected request host"}, 403)
                return False
            if token:
                authorization = self.headers.get("Authorization", "")
                if not hmac.compare_digest(authorization, "Bearer " + token):
                    self.reply({"error": "authentication_required", "message": "Enter the configured workbench access token. It stays in page memory."}, 401)
                    return False
            return True

        def do_GET(self):
            parsed = urlparse(self.path)
            path = unquote(parsed.path)
            if path.startswith("/api/"):
                if not self.authenticated():
                    return
                try:
                    if path == "/api/state":
                        payload = engine.state()
                    elif path == "/api/health":
                        payload = {"status": "ok", "mode": engine.store.metadata("mode"), "provider_calls": 0, "external_sends_from_ui": 0}
                    elif re.fullmatch(r"/api/company/[A-Z0-9.-]{1,12}", path):
                        payload = engine.company(path.rsplit("/", 1)[-1])
                    elif re.fullmatch(r"/api/company/[A-Z0-9.-]{1,12}/lab", path):
                        payload = engine.lab(path.split("/")[3])
                    elif path == "/api/runs":
                        payload = engine.runs()
                    elif re.fullmatch(r"/api/runs/run-[a-f0-9]{12,64}", path):
                        payload = engine.run_bundle(path.rsplit("/", 1)[-1])
                    elif path == "/api/reports":
                        payload = engine.reports()
                    elif re.fullmatch(r"/api/reports/[a-z0-9.-]+", path):
                        payload = engine.report(path.rsplit("/", 1)[-1])
                    elif re.fullmatch(r"/api/alerts/[a-z0-9-]+/preview", path):
                        payload = email_preview(engine.store, path.split("/")[3])
                    elif path == "/api/digest":
                        payload = digest_report(engine.state(), period=parse_qs(parsed.query).get("period", ["daily"])[0])
                    elif re.fullmatch(r"/api/assistant-packet/[A-Z0-9.-]{1,12}", path):
                        payload = engine.assistant_packet(path.rsplit("/", 1)[-1])
                    else:
                        self.reply({"error": "not_found", "message": "Unknown research endpoint"}, 404)
                        return
                    self.reply(payload)
                except ValueError as exc:
                    self.reply({"error": "invalid_request", "message": str(exc)}, 400)
                except Exception:
                    self.reply({"error": "internal_error", "message": "Research state could not be read. Existing data has been preserved."}, 500)
                return
            if not self.allowed_host():
                self.reply({"error": "host_rejected", "message": "Unexpected request host"}, 403)
                return
            filename = "index.html" if path == "/" else path.lstrip("/")
            if filename not in {"index.html", "app.css", "app.js"} or not (STATIC / filename).is_file():
                self.reply({"error": "not_found", "message": "Page not found"}, 404)
                return
            data = (STATIC / filename).read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", (mimetypes.guess_type(filename)[0] or "application/octet-stream") + "; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(data)

        def do_POST(self):
            if not self.authenticated():
                return
            origin = self.headers.get("Origin")
            same_origin = origin and urlparse(origin).netloc == self.headers.get("Host") and urlparse(origin).scheme in {"http", "https"}
            if origin and not same_origin and origin != public_origin:
                self.reply({"error": "origin_rejected", "message": "Cross-origin writes are not accepted"}, 403)
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 <= length <= MAX_BODY:
                    self.reply({"error": "body_too_large", "message": "Research request exceeds size limit"}, 413)
                    return
                if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                    raise ValueError("Request body must be application/json")
                body = json.loads(self.rfile.read(length) or b"{}", parse_constant=lambda _value: (_ for _ in ()).throw(ValueError("Nonfinite JSON is not accepted")))
                if not isinstance(body, dict):
                    raise ValueError("Request body must be an object")
                path = urlparse(self.path).path
                if path == "/api/replay":
                    result = engine.replay(body.get("event_id"))
                elif path == "/api/research":
                    result = engine.research(str(body.get("symbol", "")).upper())
                elif path == "/api/watchlist":
                    result = engine.update_watchlist(str(body.get("symbol", "")).upper(), body.get("tier", "focused"), body.get("watched", True))
                elif path == "/api/settings":
                    result = engine.update_settings(body)
                elif re.fullmatch(r"/api/company/[A-Z0-9.-]{1,12}/lab", path):
                    if set(body)-{"overrides"}:
                        raise ValueError("Sandbox accepts only parameter overrides")
                    result = engine.lab(path.split("/")[3], body.get("overrides", {}))
                elif re.fullmatch(r"/api/company/[A-Z0-9.-]{1,12}/agent", path):
                    if body:
                        raise ValueError("Browser research uses the offline planner with no external provider")
                    result = engine.run_agent(path.split("/")[3])
                elif re.fullmatch(r"/api/runs/run-[a-f0-9]{12,64}/replay", path):
                    result = engine.replay_run(path.split("/")[3])
                elif path == "/api/baseline":
                    result = engine.propose_baseline(body)
                elif path == "/api/import":
                    result = engine.import_company(body)
                elif path == "/api/events":
                    result = engine.ingest_event(body)
                elif re.fullmatch(r"/api/alerts/[a-z0-9-]+/review", path):
                    result = engine.review_alert(path.split("/")[3], body.get("action", "reviewed"))
                elif re.fullmatch(r"/api/company/[A-Z0-9.-]{1,12}/accept", path):
                    result = engine.accept_assumptions(path.split("/")[3], body["event_id"], body["baseline_hash"], body["candidate_hash"])
                else:
                    self.reply({"error": "not_found", "message": "Unknown research action"}, 404)
                    return
                self.reply(result)
            except (ValueError, KeyError, TypeError) as exc:
                self.reply({"error": "invalid_request", "message": str(exc)}, 400)
            except Exception:
                self.reply({"error": "internal_error", "message": "The action could not complete. Existing research data has been preserved."}, 500)

    server = ThreadingHTTPServer((host, port), Handler)
    server.daemon_threads = True
    return server
