"""A whole match through the real AdbDevice, against a fake `adb` that serves the battle frame
a few times, then a blank screen (match over), and records every tap it is asked to make."""

import json
import stat
from pathlib import Path

from clash_jev import runner
from clash_jev.device import AdbDevice
from clash_jev.policy import BaselinePolicy

FRAME = Path(__file__).parent / "fixtures" / "battle_419x633.png"

FAKE_ADB = """#!/bin/sh
dir="$(dirname "$0")"
if [ "$1" = "exec-out" ]; then
    count=$(cat "$dir/count" 2>/dev/null || echo 0)
    echo $((count + 1)) > "$dir/count"
    if [ "$count" -lt 3 ]; then cat "{frame}"; else cat "$dir/blank.png"; fi
elif [ "$2" = "wm" ]; then
    echo "Physical size: 419x633"
else
    echo "$@" >> "$dir/taps"
fi
"""


def test_match_is_played_and_logged(tmp_path, monkeypatch):
    import cv2
    import numpy

    cv2.imwrite(str(tmp_path / "blank.png"), numpy.full((633, 419, 3), 40, numpy.uint8))
    adb = tmp_path / "adb"
    adb.write_text(FAKE_ADB.format(frame=FRAME))
    adb.chmod(adb.stat().st_mode | stat.S_IEXEC)

    log_path = tmp_path / "runs" / "match.jsonl"
    played = runner.play_match(
        AdbDevice(adb_path=str(adb)), BaselinePolicy(play_at_elixir=4), log_path, every=0, max_decisions=1
    )

    lines = (tmp_path / "taps").read_text().splitlines()
    taps = [line for line in lines if line.startswith("shell input tap")]  # the fake adb has no open shell
    assert played >= 1
    assert taps[0] == "shell input tap 142 560"  # minions, hand slot 0
    assert taps[1] == "shell input tap 117 300"  # left_bridge
    entry = json.loads(log_path.read_text().splitlines()[0])
    assert entry["action"] == "minions -> left_bridge"
    assert entry["state"]["elixir"] == 4 and entry["state"]["left"]["mine_on_their_side"] == 1
    assert "arrows" in entry["options"]


def test_a_saved_screenshot_is_asked_about_exactly_once(tmp_path):
    from clash_jev.device import ImageDevice

    calls = []

    class CountingPolicy(BaselinePolicy):
        def decide(self, state, moves):
            calls.append(state.elixir)
            return super().decide(state, moves)

    runner.play_match(
        ImageDevice(str(FRAME)), CountingPolicy(), tmp_path / "one.jsonl", max_decisions=1, every=1
    )
    assert calls == [4]


def test_an_unchanged_board_is_not_asked_about_again(tmp_path, monkeypatch):
    """A board identical in every field Jev sees is asked about once, not once per frame."""
    from clash_jev.device import ImageDevice
    from clash_jev.policy import Decision

    calls = []

    class Waiter:
        def decide(self, state, moves):
            calls.append(state.elixir)
            return Decision(None, None, "jev", {"requests_made": 1})

    frames = iter(range(6))
    device = ImageDevice(str(FRAME))
    real_frame = device.frame

    def limited():
        next(frames)  # six identical frames, then StopIteration ends the run
        return real_frame()

    device.frame = limited
    try:
        runner.play_match(device, Waiter(), tmp_path / "static.jsonl", every=0)
    except StopIteration:
        pass
    # The picture never changes, so six frames get one question. On a slow machine the six frames can take over
    # four seconds, and then the enemy tower that shows no bar is reported destroyed. That change is asked about once.
    assert calls in ([4], [4, 4])


def test_jev_is_asked_even_when_no_card_is_affordable(tmp_path):
    """An empty elixir bar does not stop the question from being asked."""
    from clash_jev.device import ImageDevice

    asked = []

    class Recorder(BaselinePolicy):
        def decide(self, state, moves):
            asked.append((state.elixir, [card.ready for card in state.hand], len(moves)))
            return super().decide(state, moves)

    grey = FRAME.with_name("tablet_hand_grey.png")  # 0 elixir, every card greyed
    runner.play_match(ImageDevice(str(grey)), Recorder(), tmp_path / "grey.jsonl", max_decisions=1, every=0)
    assert asked == [(0, [False] * 4, 0)]


def test_after_jev_chooses_to_wait_it_is_asked_again_once_elixir_has_gone_up(tmp_path, monkeypatch):
    import itertools
    from dataclasses import replace

    from clash_jev.policy import Decision
    from clash_jev.units import Unit

    steps = itertools.count()

    elixirs = iter([3, 3, 3, 4, 4, 5, 10, 10, 10])
    asked = []

    class Saver:
        def decide(self, state, moves):
            asked.append((state.elixir, round(state.seconds_at_full_elixir)))
            return Decision(None, None, "jev", {"strategy_choice": "save_elixir", "requests_made": 1})

    class Scripted(runner.Perception):
        def extract_state(self, frame, elapsed_s=0.0):
            state = super().extract_state(frame, elapsed_s)
            # Troops move between snapshots in a real match, so every snapshot is a new state.
            moving = (Unit("mine", 0.3, round(0.2 + next(steps) * 0.001, 3), None),)
            return replace(state, elixir=next(elixirs), units=moving)

    monkeypatch.setattr(runner, "Perception", Scripted)  # the runner's reader only: other threads keep theirs
    try:
        from clash_jev.device import ImageDevice

        runner.play_match(ImageDevice(str(FRAME)), Saver(), tmp_path / "wait.jsonl", every=0)
    except StopIteration:
        pass
    # Jev keeps choosing save_elixir: asked at 3, not again at 3, asked at 4 and at 5; at 10 elixir cannot rise,
    # so the pause never applies there.
    assert [elixir for elixir, _ in asked] == [3, 4, 5, 10, 10, 10]


def test_a_new_enemy_troop_or_a_hit_on_my_tower_is_asked_about_at_once(tmp_path, monkeypatch):
    import time
    from dataclasses import replace

    from clash_jev.policy import Decision
    from clash_jev.units import Unit

    # Elixir never rises in this script, so after the first question only the two events can cause another.
    script = iter(
        [
            ("quiet", (), 1.0),
            ("quiet", (), 1.0),
            ("an enemy giant arrives", (Unit("enemy", 0.3, 0.30, None, "giant", seen_for_s=0.0),), 1.0),
            ("the same giant, walking", (Unit("enemy", 0.3, 0.32, None, "giant", seen_for_s=50.0),), 1.0),
            ("my left tower is hit", (Unit("enemy", 0.3, 0.34, None, "giant", seen_for_s=51.0),), 0.8),
            (
                "same health, a wobble in the reading",
                (Unit("enemy", 0.3, 0.36, None, "giant", seen_for_s=52.0),),
                0.79,
            ),
        ]
    )
    asked = []
    current = {}

    class Saver:
        def decide(self, state, moves):
            asked.append(current["what"])
            return Decision(None, None, "jev", {"strategy_choice": "save_elixir", "requests_made": 1})

    class Scripted(runner.Perception):
        def extract_state(self, frame, elapsed_s=0.0):
            state = super().extract_state(frame, elapsed_s)
            current["what"], units, my_left = next(script)
            time.sleep(0.01)  # the clock moves between snapshots
            return replace(state, elixir=3, units=units, towers=replace(state.towers, my_left=my_left))

    monkeypatch.setattr(runner, "Perception", Scripted)
    try:
        from clash_jev.device import ImageDevice

        runner.play_match(ImageDevice(str(FRAME)), Saver(), tmp_path / "events.jsonl", every=0)
    except StopIteration:
        pass
    assert asked == ["quiet", "an enemy giant arrives", "my left tower is hit"]


def test_after_a_play_jev_is_not_asked_about_the_board_from_before_it(tmp_path, monkeypatch):
    from dataclasses import replace

    from clash_jev.moves import ALL_SQUARES
    from clash_jev.policy import Decision

    elixirs = iter([8, 8, 8, 3, 4])  # the play costs 5; the video shows it two snapshots later
    asked = []

    class Pusher:
        def decide(self, state, moves):
            asked.append(state.elixir)
            return Decision(
                state.hand[0], ALL_SQUARES["left_bridge"], "jev", {"strategy_choice": "push_left"}
            )

    class Scripted(runner.Perception):
        def extract_state(self, frame, elapsed_s=0.0):
            return replace(super().extract_state(frame, elapsed_s), elixir=next(elixirs), elapsed_s=elapsed_s)

    monkeypatch.setattr(runner, "Perception", Scripted)
    monkeypatch.setattr(runner, "play_card", lambda *args: None)
    try:
        from clash_jev.device import ImageDevice

        runner.play_match(ImageDevice(str(FRAME)), Pusher(), tmp_path / "settle.jsonl", every=0)
    except StopIteration:
        pass
    assert asked == [
        8,
        3,
    ]  # not the two stale snapshots still showing 8; and not 4: that play is settling too


def test_a_run_is_recorded_as_a_video_whose_clock_is_the_runs_clock(tmp_path):
    import time

    import av
    import numpy

    from clash_jev.record import Recorder

    def frame():
        return numpy.full((1152, 720, 3), int(time.time() * 50) % 255, numpy.uint8)

    recorder = Recorder(frame, tmp_path / "runs" / "match.mp4", started=time.time(), fps=10)
    time.sleep(1.2)
    recorder.stop()
    with av.open(str(tmp_path / "runs" / "match.mp4")) as video:
        stream = video.streams.video[0]
        pictures = [picture for picture in video.decode(stream)]
    assert (stream.width, stream.height) == (480, 768)
    assert 8 <= len(pictures) <= 13 and 0.8 <= float(pictures[-1].pts * stream.time_base) <= 1.3
