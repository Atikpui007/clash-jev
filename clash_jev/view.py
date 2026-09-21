"""Live viewer: the emulator screen on the left; the state, the questions sent and Jev's answer on the right.

A tiny local web server the match loop publishes to. The page polls it twice a second.
"""

import json
import mimetypes
import re
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import cv2
import numpy

from clash_jev.screenmap import ScreenMap
from clash_jev.state import BattleState

# The page is the project's web app (web/, built with `npm run build`). It is looked for inside the
# installed package first, then in a source checkout. Replays are read from where `clash-jev publish`
# writes them, so a new replay shows without rebuilding the app.
_APP_FOLDERS = (Path(__file__).with_name("webapp"), Path(__file__).parent.parent / "web" / "out")
_REPLAYS = Path(__file__).parent.parent / "web" / "public" / "replays"
_JEV_API = "https://api.typesafe.ai/v1/systemone"
_NO_APP = (
    b"The bot is running, but its page has not been built yet.\n"
    b"In a source checkout:  cd web && npm install && npm run build   then reload this page.\n"
)


def _app_file(route: str) -> Path | None:
    """The file behind a URL of the web app, never one outside its folders."""
    relative = route.lstrip("/") or "index.html"
    roots = (_REPLAYS.parent, *_APP_FOLDERS) if relative.startswith("replays/") else _APP_FOLDERS
    for root in roots:
        for candidate in (root / relative, root / f"{relative}.html", root / relative / "index.html"):
            resolved = candidate.resolve()
            if resolved.is_file() and root.resolve() in resolved.parents:
                return resolved
    return None


def annotate(
    frame: numpy.ndarray, state: BattleState | None, square_xy: tuple[float, float] | None, width: int = 838
) -> numpy.ndarray:
    """The frame as the bot sees it: troops circled by owner, the chosen square marked."""
    height = round(frame.shape[0] * width / frame.shape[1])
    shrink = width < frame.shape[1]
    canvas = cv2.resize(frame, (width, height), interpolation=cv2.INTER_AREA if shrink else cv2.INTER_LINEAR)
    if state is None:
        return canvas
    unit = width / 838  # marker sizes were designed at 838 px wide
    # Readings are on the reference layout. The picture is the device's own, so map them back onto it.
    screen = ScreenMap(width, height)
    for troop in state.units:
        colour = (60, 60, 255) if troop.owner == "enemy" else (255, 160, 40)
        centre = screen.to_device((troop.x, troop.y + 0.03))
        cv2.circle(canvas, centre, int(34 * unit), colour, max(2, int(3 * unit)))
        if troop.name:
            where = (centre[0] - int(34 * unit), centre[1] + int(56 * unit))
            cv2.putText(canvas, troop.name, where, cv2.FONT_HERSHEY_SIMPLEX, 0.6 * unit + 0.15, colour, 2)
    if square_xy:
        point = screen.to_device(square_xy)
        cv2.drawMarker(canvas, point, (80, 255, 120), cv2.MARKER_CROSS, int(44 * unit), max(2, int(4 * unit)))
        cv2.circle(canvas, point, int(26 * unit), (80, 255, 120), max(2, int(3 * unit)))
    return canvas


_BULKY = ("request", "state", "options")


class LiveView:
    def __init__(self, port: int = 8765):
        self.port = port
        self._jpeg = b""
        self._payload = b"{}"
        self._history: list[dict] = []
        self._last_play: dict | None = None  # the newest decision in which Jev picked a card
        self._units: list[
            dict
        ] = []  # where the troops are right now, for a page that draws them over the video
        self.progress: dict = {}
        self._boot = int(time.time())  # changes when the bot process restarts, so the page can reconnect
        self.frame_source = None  # callable -> newest device frame; enables the smooth /stream.mjpg feed
        self._overlay: tuple[BattleState, tuple[float, float] | None] | None = None
        self.controller = None  # set by control.Controller: gives the page its Start / Stop buttons
        view = self

        class Handler(BaseHTTPRequestHandler):
            def _allow_local_page(self):
                """Allows cross-origin requests only from pages served on this machine."""
                origin = self.headers.get("Origin") or ""
                if re.fullmatch(r"https?://(localhost|127\.0\.0\.1)(:\d+)?", origin):
                    self.send_header("Access-Control-Allow-Origin", origin)
                    self.send_header("Vary", "Origin")

            def do_OPTIONS(self):
                self.send_response(204)
                self._allow_local_page()
                self.send_header("Access-Control-Allow-Methods", "GET, POST")
                self.send_header("Access-Control-Allow-Headers", "Content-Type")
                self.end_headers()

            def do_GET(self):
                route = self.path.split("?")[0]
                if route == "/stream.mjpg" and view.frame_source is not None:
                    return self._stream()
                if route == "/latest.json":
                    return self._answer(view.payload(), "application/json")
                if route == "/frame.jpg":
                    return self._answer(view._jpeg, "image/jpeg")
                self._file(route)

            def _answer(self, body: bytes, kind: str, status: int = 200) -> None:
                self.send_response(status)
                self.send_header("Content-Type", kind)
                self.send_header("Cache-Control", "no-store")
                self._allow_local_page()
                self.end_headers()
                self.wfile.write(body)

            def _file(self, route: str) -> None:
                """Serves the web app and the published replays as plain files. Byte ranges are supported
                so that a video can be scrubbed."""
                found = _app_file(route)
                if found is None:
                    return self._answer(
                        _NO_APP if route == "/" else b"not found", "text/plain; charset=utf-8", 404
                    )
                size = found.stat().st_size
                start, end = 0, size - 1
                asked = re.fullmatch(r"bytes=(\d*)-(\d*)", self.headers.get("Range") or "")
                if asked and (asked.group(1) or asked.group(2)):
                    if asked.group(1):
                        start, end = int(asked.group(1)), min(int(asked.group(2) or size - 1), size - 1)
                    else:  # "the last N bytes"
                        start = max(0, size - int(asked.group(2)))
                    if start > end:
                        self.send_response(416)
                        self.send_header("Content-Range", f"bytes */{size}")
                        return self.end_headers()
                self.send_response(206 if asked else 200)
                self.send_header(
                    "Content-Type", mimetypes.guess_type(found.name)[0] or "application/octet-stream"
                )
                hashed = "/_next/static/" in route
                self.send_header(
                    "Cache-Control", "public, max-age=31536000, immutable" if hashed else "no-store"
                )
                self.send_header("Accept-Ranges", "bytes")
                self.send_header("Content-Length", str(end - start + 1))
                if asked:
                    self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
                self.end_headers()
                with found.open("rb") as file:
                    file.seek(start)
                    left = end - start + 1
                    while left > 0 and (chunk := file.read(min(1 << 16, left))):
                        try:
                            self.wfile.write(chunk)
                        except (BrokenPipeError, ConnectionResetError):
                            return  # the browser stopped listening: it only wanted the start of the video
                        left -= len(chunk)

            def _stream(self):
                """Motion-JPEG: the device's own video, with the latest readings drawn on each picture."""
                self.send_response(200)
                self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                source = getattr(view.frame_source, "__self__", None)
                shown = -1
                try:
                    while True:
                        # Send a picture only when the device has produced a new one, up to ~30 a second.
                        current = getattr(source, "frame_id", None)
                        if current is not None and current == shown:
                            time.sleep(0.005)
                            continue
                        shown = current
                        picture = view.frame_source()
                        state, square = view._overlay or (None, None)
                        picture = annotate(picture, state, square, width=540)
                        ok, jpeg = cv2.imencode(".jpg", picture, [cv2.IMWRITE_JPEG_QUALITY, 70])
                        if ok:
                            data = jpeg.tobytes()
                            head = (
                                f"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: {len(data)}\r\n\r\n"
                            )
                            self.wfile.write(head.encode() + data + b"\r\n")
                        time.sleep(1 / 35)
                except (BrokenPipeError, ConnectionResetError):
                    pass

            def _reask(self, sent: bytes) -> None:
                """The replay's "Re-ask Jev" panel: one question, passed on to TypeSafe with the key typed
                into the page. The API does not accept calls made straight from a web page. Nothing is
                logged or kept."""
                status, reply = 400, b'{"error": "one question per request"}'
                try:
                    asked = json.loads(sent or b"{}")
                    if isinstance(asked.get("questions"), dict) and len(asked["questions"]) == 1:
                        body = {
                            "state": asked.get("state"),
                            "model": "jev-latest",
                            "questions": asked["questions"],
                        }
                        request = urllib.request.Request(
                            _JEV_API,
                            json.dumps(body).encode(),
                            {
                                "Authorization": self.headers.get("Authorization") or "",
                                "Content-Type": "application/json",
                            },
                        )
                        with urllib.request.urlopen(request, timeout=15) as answered:
                            status, reply = answered.status, answered.read()
                except urllib.error.HTTPError as error:
                    status, reply = error.code, error.read()
                except (OSError, ValueError) as error:
                    status, reply = 502, json.dumps({"error": type(error).__name__}).encode()
                self._answer(reply, "application/json", status)

            def do_POST(self):
                length = int(self.headers.get("Content-Length") or 0)
                if self.path == "/api/jev":
                    return self._reask(self.rfile.read(min(length, 400_000)))
                body = json.loads(self.rfile.read(length) or b"{}")
                if view.controller is None:
                    result = {"error": "this page was opened without controls"}
                elif self.path == "/start":
                    result = view.controller.start(body)
                elif self.path == "/stop":
                    result = view.controller.stop()
                else:
                    result = {"error": "unknown"}
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self._allow_local_page()
                self.end_headers()
                self.wfile.write(json.dumps(result).encode())

            def log_message(self, *_):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        print(f"Viewer: http://127.0.0.1:{port}")

    def payload(self) -> bytes:
        status = self.controller.status() if self.controller else None
        extra = {"control": status, "live_video": self.frame_source is not None, "boot": self._boot}
        return json.dumps({**json.loads(self._payload), **extra}).encode()

    def clear_history(self) -> None:
        self._history = []
        self._last_play = None

    def publish(
        self, frame: numpy.ndarray, state: BattleState, sent_state: dict, decision: dict | None
    ) -> None:
        """`decision` is the newest log entry, or None on frames where Jev was not asked."""
        if decision is not None:
            # Only the newest decision and the last one with a card pick are kept in full. Earlier
            # decisions drop the state and questions that were sent.
            slim = [{key: value for key, value in old.items() if key not in _BULKY} for old in self._history]
            self._history = [decision, *slim][:60]
            if decision.get("card_choice"):
                self._last_play = decision
        self._units = [
            {"owner": unit.owner, "x": unit.x, "y": unit.y, "name": unit.name, "health": unit.health}
            for unit in state.units
        ]
        latest = self._history[0] if self._history else None
        square = (latest or {}).get("square_xy")
        self._overlay = (state, square)
        if self.frame_source is not None:  # the page shows the video feed; no still picture is needed
            self._payload = self._page_data(sent_state)
            return
        ok, jpeg = cv2.imencode(".jpg", annotate(frame, state, square), [cv2.IMWRITE_JPEG_QUALITY, 80])
        if ok:
            self._jpeg = jpeg.tobytes()
        self._payload = self._page_data(sent_state)

    def _page_data(self, sent_state: dict) -> bytes:
        return json.dumps(
            {
                "state": sent_state,
                "history": self._history,
                "last_play": self._last_play,
                "units": self._units,
            }
        ).encode()
