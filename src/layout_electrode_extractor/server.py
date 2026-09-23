"""Loopback-only review server with fixed artifact allowlist and JSON writes."""

from __future__ import annotations

import json
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from pathlib import Path
from urllib.parse import unquote, urlsplit

from .review import ReviewError, ReviewProject, StaleAnnotationsError


class ReviewServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address: tuple[str, int], project: ReviewProject):
        host, _ = address
        if host not in {"127.0.0.1", "::1", "localhost"}:
            raise ReviewError("review server may bind only to loopback")
        super().__init__(address, ReviewHandler)
        self.project = project
        self.csrf = secrets.token_urlsafe(32)
        self.write_lock = threading.Lock()


class ReviewHandler(BaseHTTPRequestHandler):
    server: ReviewServer

    def _allowed_origin(self) -> bool:
        host = self.headers.get("Host", "")
        hostname = host.rsplit(":", 1)[0].strip("[]")
        if hostname not in {"127.0.0.1", "::1", "localhost"}:
            return False
        origin = self.headers.get("Origin")
        return origin is None or origin == f"http://{host}"

    def _send(self, status: int, data: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self'; script-src 'self'; "
            "style-src 'self'; object-src 'none'; base-uri 'none'",
        )
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def do_HEAD(self) -> None:
        self.do_GET()

    def _json(self, status: int, value: object) -> None:
        self._send(
            status,
            json.dumps(value, ensure_ascii=False).encode(),
            "application/json; charset=utf-8",
        )

    def _error(self, status: int, message: str) -> None:
        self._json(status, {"error": message})

    def do_GET(self) -> None:
        if not self._allowed_origin():
            self._error(403, "loopback host required")
            return
        path = urlsplit(self.path).path
        if path in {"/", "/index.html"}:
            data = (
                resources.files("layout_electrode_extractor")
                .joinpath("static/index.html")
                .read_bytes()
            )
            self._send(200, data, "text/html; charset=utf-8")
            return
        if path in {"/static/app.js", "/static/style.css"}:
            data = (
                resources.files("layout_electrode_extractor")
                .joinpath(path.lstrip("/"))
                .read_bytes()
            )
            mime = (
                "text/javascript; charset=utf-8"
                if path.endswith(".js")
                else "text/css; charset=utf-8"
            )
            self._send(200, data, mime)
            return
        if path == "/api/state":
            with self.server.write_lock:
                state = self.server.project.state()
            state["csrf"] = self.server.csrf
            self._json(200, state)
            return
        if path == "/api/schematic" and self.server.project.schematic_path:
            image = self.server.project.schematic_path
            mime = "image/png" if image.suffix.lower() == ".png" else "image/jpeg"
            self._send(200, image.read_bytes(), mime)
            return
        if path.startswith("/api/asset/"):
            relative = unquote(path[len("/api/asset/") :])
            if relative not in self.server.project.allowed_assets or not relative.endswith(".png"):
                self._error(404, "unknown mask")
                return
            try:
                data = self.server.project._path(relative).read_bytes()
            except (OSError, ReviewError):
                self._error(404, "mask unavailable")
                return
            self._send(200, data, "image/png")
            return
        self._error(404, "unknown endpoint")

    def do_POST(self) -> None:
        if not self._allowed_origin() or self.headers.get("X-Review-Token") != self.server.csrf:
            self._error(403, "invalid origin or review token")
            return
        if self.headers.get("Content-Type", "").split(";", 1)[0] != "application/json":
            self._error(415, "JSON request required")
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length < 1 or length > 1_000_000:
                raise ReviewError("request must be 1..1000000 bytes")
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict):
                raise ReviewError("request must be an object")
            path = urlsplit(self.path).path
            with self.server.write_lock:
                if path == "/api/save":
                    if set(payload) != {"annotations", "revision"}:
                        raise ReviewError("save requires annotations and revision")
                    revision = self.server.project.save_annotations(
                        payload["annotations"], payload["revision"]
                    )
                    self._json(
                        200,
                        {
                            "revision": revision,
                            "suggestions": self.server.project.state()["suggestions"],
                        },
                    )
                    return
                if path == "/api/export":
                    if payload:
                        raise ReviewError("export takes an empty object")
                    root = self.server.project.root
                    output = self.server.project.export(root.parent / f"{root.name}-reviewed")
                    self._json(200, {"output": str(output)})
                    return
            self._error(404, "unknown endpoint")
        except (ReviewError, OSError, ValueError, json.JSONDecodeError) as exc:
            status = 409 if isinstance(exc, StaleAnnotationsError) else 400
            self._error(status, str(exc))


def serve_review(
    extraction: str | Path,
    *,
    circuit: str | Path | None = None,
    schematic: str | Path | None = None,
    host: str = "127.0.0.1",
    port: int = 8765,
) -> None:
    project = ReviewProject(extraction, circuit, schematic)
    with ReviewServer((host, port), project) as server:
        print(f"Review at http://{host}:{server.server_address[1]}/", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
