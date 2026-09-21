"""Start and Stop a run from the viewer page.

While idle the page mirrors the device and shows the readings, with no Jev requests. A run lasts until Stop
is pressed or the request cap is reached. An answer still in flight at Stop is discarded. One run at a time.
"""

import os
import threading
import time
from pathlib import Path

from clash_jev.collect import collected
from clash_jev.device import StreamDevice
from clash_jev.perception import Perception
from clash_jev.policy import JevPolicy, build_state
from clash_jev.runner import play_match
from clash_jev.tracks import TroopWatcher
from clash_jev.view import LiveView


class Controller:
    def __init__(self, device: StreamDevice, view: LiveView, policy_factory=JevPolicy):
        self.device, self.view = device, view
        view.controller = self
        view.frame_source = device.frame
        self._run: threading.Thread | None = None
        self._stop = threading.Event()
        self._mode = "idle"
        self._starting = False
        self._events: list[str] = []
        self._cap: int | None = None
        self._message = "Ready."
        self._policy = None
        self._policy_factory = policy_factory
        # One watcher follows the troops for both the idle mirror and a run. It makes no Jev requests.
        self.watcher = TroopWatcher(device.frame, Perception().read_troops)
        threading.Thread(target=self._mirror, daemon=True).start()

    @property
    def running(self) -> bool:
        return self._run is not None and self._run.is_alive()

    def status(self) -> dict:
        progress = self.view.progress if self.running else {}
        return {
            "running": self.running,
            "mode": self._mode,
            "cap": self._cap,
            "message": self._message,
            "events": self._events,
            "troop_reads": self.watcher.reads,
            **progress,
        }

    def _log(self, event: str) -> None:
        self._events = [f"{time.strftime('%H:%M:%S')} {event}", *self._events][:6]

    def _mirror(self) -> None:
        """Idle: keep the page showing the live screen and the readings. Makes no Jev requests."""
        perception = Perception(watcher=self.watcher)
        while True:
            try:
                if not self.running and not self._starting:
                    frame = self.device.frame()
                    state = perception.extract_state(frame)
                    # A run may have begun while this frame was read.
                    if not self.running and not self._starting:
                        self.view.publish(frame, state, build_state(state), None)
                    if self._message.startswith("Cannot read the device"):
                        self._message = "Ready."  # it is back
            except Exception as error:  # noqa: BLE001 (an unplugged device must not end the mirror)
                self._message = f"Cannot read the device ({type(error).__name__}). Is it still plugged in?"
                time.sleep(2)
            time.sleep(0.5)

    def _collect(self) -> None:
        """Watch a match played by hand and save pictures for training the troop network.

        No Jev request is made and nothing is tapped."""
        try:
            os.environ.setdefault("CLASH_JEV_COLLECT", str(Path("runs/troops").resolve()))
            before = dict(collected)
            perception = Perception(watcher=self.watcher)
            while not self._stop.is_set():
                frame = self.device.frame()
                state = perception.extract_state(frame)
                self.view.publish(frame, state, build_state(state), None)
                frames, pictures = (collected[kind] - before.get(kind, 0) for kind in ("frames", "pictures"))
                self._message = (
                    f"Collecting — you play, the bot only watches: {frames} frames and {pictures} troop pictures "
                    f"saved to {os.environ['CLASH_JEV_COLLECT']}. No Jev requests. Press Stop to end."
                )
                time.sleep(0.4)
            self._log(f"Collection ended: {frames} frames, {pictures} troop pictures")
            self._message = (
                f"Collected {frames} frames and {pictures} troop pictures. Name them with: clash-jev label"
            )
        except Exception as error:  # noqa: BLE001 (show the failure on the page)
            self._message = f"Collection stopped on an error: {error!r}"
        finally:
            self._mode = "idle"

    def start(self, options: dict) -> dict:
        if self.running or self._starting:
            return {"error": "already running"}
        self._starting = True
        dry_run = bool(options.get("dry_run"))
        collect = bool(options.get("collect"))
        self._log("Collect pressed" if collect else f"Start pressed ({'dry run' if dry_run else 'playing'})")
        self._cap = max(1, int(options.get("max_requests") or 250))
        every = max(0.2, float(options.get("every") or 1.0))
        self._mode = "collecting" if collect else "dry run" if dry_run else "playing"
        self._stop.clear()
        self.view.clear_history()
        self.view.progress = {}

        def run() -> None:
            if collect:
                return self._collect()
            try:
                self.device.dry_run = dry_run
                self._policy = self._policy or self._policy_factory()
                self._message = (
                    "Running — every snapshot that shows your hand goes to Jev. Press Stop to end."
                )
                log_path = Path("runs") / f"{time.strftime('%Y%m%d-%H%M%S')}-jev.jsonl"
                cards = play_match(
                    self.device,
                    self._policy,
                    log_path,
                    self.view,
                    max_requests=self._cap,
                    every=every,
                    should_stop=self._stop.is_set,
                    watcher=self.watcher,
                    record=True,
                )
                done = self.view.progress
                self._log(f"Run ended: {done.get('requests', 0)} Jev requests")
                self._message = (
                    f"Finished: {cards} cards played, {done.get('decisions', 0)} decisions, "
                    f"{done.get('requests', 0)} Jev requests. Log: {log_path}"
                )
            except Exception as error:  # noqa: BLE001 (show the failure on the page)
                self._message = f"Stopped on an error: {error!r}"
            finally:
                self._mode = "idle"

        self._run = threading.Thread(target=run, daemon=True)
        self._run.start()
        self._starting = False
        return {"ok": True}

    def stop(self) -> dict:
        self._log("Stop pressed")
        self._stop.set()
        self._message = "Stopping..."
        return {"ok": True}
