"""The page's Start / Stop: one run at a time, the cap is honoured, Stop ends it, idle asks nothing."""

import time
from pathlib import Path

from clash_jev.control import Controller
from clash_jev.device import ImageDevice
from clash_jev.policy import Decision

FRAME = Path(__file__).parent / "fixtures" / "battle_419x633.png"


class FakeView:
    port = 0

    def __init__(self):
        self.progress, self.controller, self.published = {}, None, 0

    def publish(self, *_):
        self.published += 1

    def clear_history(self):
        pass


def _wait(condition, seconds=40.0):  # the first screen read also loads the troop network
    deadline = time.time() + seconds
    while not condition() and time.time() < deadline:
        time.sleep(0.02)
    return condition()


def test_start_runs_until_stop_and_idle_never_asks(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    asked = []

    class Saver:
        def decide(self, state, moves):
            asked.append(state.elixir)
            return Decision(None, None, "jev", {"requests_made": 1, "strategy_choice": "save_elixir"})

    device = ImageDevice(str(FRAME))
    device.dry_run = False
    controller = Controller(device, FakeView(), policy_factory=Saver)

    assert _wait(lambda: controller.view.published > 0) and asked == []  # mirroring, no questions
    assert controller.status()["running"] is False

    assert controller.start({"dry_run": True, "max_requests": 50, "every": 0.2}) == {"ok": True}
    assert _wait(lambda: len(asked) == 1)
    assert controller.start({}) == {"error": "already running"}
    assert device.dry_run is True and controller.status()["mode"] == "dry run"

    controller.stop()
    assert _wait(lambda: not controller.running)
    assert len(asked) == 1  # the unchanged board was asked about once, then Stop ended the run
    assert controller.status()["mode"] == "idle"


def test_the_request_cap_ends_the_run(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    class Spender:
        def decide(self, state, moves):
            return Decision(None, None, "jev", {"requests_made": 3, "strategy_choice": "save_elixir"})

    device = ImageDevice(str(FRAME))
    device.dry_run = False
    controller = Controller(device, FakeView(), policy_factory=Spender)
    controller.start({"dry_run": True, "max_requests": 2, "every": 0.2})
    assert _wait(lambda: not controller.running)
    assert "3 Jev requests" in controller.status()["message"]


def test_only_stop_ends_a_run_whatever_is_on_screen(tmp_path, monkeypatch):
    """Start is the battle signal and Stop ends it. A menu or results screen mid-run changes nothing."""
    import cv2
    import numpy

    monkeypatch.chdir(tmp_path)
    battle = cv2.imread(str(FRAME))
    asked = []

    class Saver:
        def decide(self, state, moves):
            asked.append(round(state.elapsed_s, 1))
            return Decision(None, None, "jev", {"requests_made": 1, "strategy_choice": "save_elixir"})

    device = ImageDevice(str(FRAME))
    device.dry_run = False
    showing = {"frame": battle}
    device.frame = lambda: showing["frame"].copy()
    controller = Controller(device, FakeView(), policy_factory=Saver)
    controller.start({"dry_run": True, "max_requests": 50, "every": 0.05})
    assert _wait(lambda: len(asked) == 1)
    assert asked[0] < 2.0  # the clock counts from the Start press

    showing["frame"] = numpy.full_like(battle, 40)  # a screen with no hand on it
    time.sleep(0.6)
    assert controller.running and len(asked) == 1  # nothing to ask about, and the run carries on

    controller.stop()
    assert _wait(lambda: not controller.running)


def test_stop_discards_a_decision_that_was_in_flight(tmp_path, monkeypatch):
    """Pressing Stop while an answer is in flight must not let the answered card be played."""
    monkeypatch.chdir(tmp_path)
    taps = []
    holder = {}

    class SlowPlayer:
        def decide(self, state, moves):
            holder["controller"].stop()  # Stop arrives while "Jev" is still answering
            return Decision(
                moves[0].card, moves[0].squares[0], "jev", {"requests_made": 3, "strategy_choice": "x"}
            )

    device = ImageDevice(str(FRAME))
    device.dry_run = False
    device.play = lambda card_xy, square_xy: taps.append((card_xy, square_xy))
    controller = Controller(device, FakeView(), policy_factory=SlowPlayer)
    holder["controller"] = controller
    controller.start({"dry_run": False, "max_requests": 50, "every": 0.05})
    assert _wait(lambda: not controller.running)
    assert taps == []
    assert "3 Jev requests" in controller.status()["message"]  # the request was made and is counted


def test_collect_watches_and_saves_pictures_without_asking_jev_or_tapping(tmp_path, monkeypatch):
    monkeypatch.setenv("CLASH_JEV_COLLECT", str(tmp_path))
    asked, taps = [], []

    class Policy:
        def decide(self, state, moves):
            asked.append(state.elixir)
            raise AssertionError("collecting must never ask Jev")

    device = ImageDevice(str(FRAME))
    device.tap = lambda x, y: taps.append((x, y))
    device.play = lambda *args: taps.append(args)
    controller = Controller(device, FakeView(), policy_factory=Policy)
    assert controller.start({"collect": True}) == {"ok": True}
    assert _wait(lambda: len(list(tmp_path.rglob("frames/*.jpg"))) >= 1)
    assert _wait(lambda: "No Jev requests" in controller.status()["message"])
    assert controller.status()["mode"] == "collecting"
    controller.stop()
    assert _wait(lambda: not controller.running)
    assert asked == [] and taps == [] and "Collected" in controller.status()["message"]
    assert list(tmp_path.rglob("mine/*/*.jpg"))  # my giant in the frame was saved as a troop picture
