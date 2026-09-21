"""One match: repeat capture -> state -> valid moves -> policy -> clicks, logging every decision."""

import json
import time
from dataclasses import asdict, replace
from pathlib import Path

import cv2

from clash_jev.cards import info
from clash_jev.device import AdbDevice
from clash_jev.moves import get_valid_moves
from clash_jev.perception import Perception, to_reference
from clash_jev.pipeline import play_card
from clash_jev.policy import Policy, build_state
from clash_jev.record import Recorder
from clash_jev.strategies import NO_PLAY
from clash_jev.view import LiveView

_MAX_ELIXIR = 10
_PLAY_SHOWS_WITHIN_S = 2.5  # a play that has not shown on screen by then did not happen (a mistimed tap)
_TOWER_HIT = 0.03  # a smaller change in a tower's bar is reading noise


def play_match(
    device: AdbDevice,
    policy: Policy,
    log_path: Path,
    view: LiveView | None = None,
    max_decisions: int | None = None,
    max_requests: int | None = None,
    every: float = 1.0,
    should_stop=lambda: False,
    watcher=None,
    record: bool = False,
) -> int:
    """Runs from now until `should_stop()`, `max_requests` or `max_decisions`. Nothing on screen ends it.

    There is no screen-based battle detection. The match clock counts from the start of the run.
    A screen on which no hand card can be read (a menu, the end of a match) is skipped.
    `every` is the time in seconds between snapshots. `max_requests` is a hard budget on Jev
    requests (saving elixir costs one, a play up to three: strategy, card, square).
    """
    started = time.time()
    recorder = Recorder(device.frame, log_path.with_suffix(".mp4"), started) if record else None
    try:
        return _play(
            device, policy, log_path, view, max_decisions, max_requests, every, should_stop, watcher, started
        )
    finally:
        if recorder is not None:
            recorder.stop()  # closes the video file, also when the run ends on an error


def _play(
    device, policy, log_path, view, max_decisions, max_requests, every, should_stop, watcher, started
) -> int:

    decisions = requests = 0
    last_snapshot = 0.0
    log_path.parent.mkdir(parents=True, exist_ok=True)
    perception = Perception(watcher=watcher)
    last_signature = None
    settling: tuple | None = None  # (elixir, hand) when a card was just played, and when
    waiting_at: int | None = None  # my elixir when Jev last chose to play nothing
    asked_at = 0.0
    towers_asked: tuple = (None, None, None)  # my towers' health at the last question
    plays: list[tuple[str, str, float]] = []

    with log_path.open("a", encoding="utf-8") as log:
        while not should_stop():
            if view is not None:
                view.progress = {"requests": requests, "decisions": decisions, "cards_played": len(plays)}
            # One snapshot per `every` seconds. Reading the full state more often starves the video decoder.
            wait = last_snapshot + every - time.time()
            if wait > 0:
                time.sleep(min(wait, 0.05))
                continue
            last_snapshot = time.time()
            screenshot = device.frame()
            now = time.time()
            state = replace(perception.extract_state(screenshot, now - started), snapshot_interval_s=every)
            if view is not None:
                view.publish(screenshot, state, build_state(state), None)

            options = get_valid_moves(state)
            if all(card.name == "unknown" for card in state.hand):
                continue
            # After a play the screen needs a moment to show it. Until the elixir has dropped or the hand has
            # changed, the snapshot is still the board from before the play, so it is skipped.
            if settling is not None:
                before, since = settling
                shown = state.elixir < before[0] or tuple(card.name for card in state.hand) != before[1]
                if not shown and now - since < _PLAY_SHOWS_WITHIN_S:
                    continue
                settling = None
            # A state identical in every sent field to the one just answered is not sent again.
            leak = round(
                state.seconds_at_full_elixir
            )  # grows while at 10, so a leaking board is asked about again
            # How long a troop has been followed grows with the clock alone. It is not a change on the board.
            board = tuple(
                replace(unit, seen_for_s=None, played_as=None, unseen_for_s=0.0) for unit in state.units
            )
            signature = (state.elixir, leak, state.hand, state.left, state.right, state.towers, board)
            if signature == last_signature:
                continue
            # After save_elixir or hold_elixir_for_threat, no request is made until the elixir has gone up
            # (at 10 it cannot, so there the pause never applies). Two events end that pause at once: an enemy
            # troop that was not there at the last request, and damage to one of my towers since then.
            waiting = waiting_at is not None and state.elixir <= waiting_at < _MAX_ELIXIR
            arrived = any(
                unit.owner == "enemy" and unit.seen_for_s is not None and unit.seen_for_s < now - asked_at
                for unit in state.units
            )
            mine = (state.towers.my_left, state.towers.my_right, state.towers.my_king)
            hit = any(
                before is not None and after is not None and after < before - _TOWER_HIT
                for before, after in zip(towers_asked, mine)
            )
            if waiting and not (arrived or hit):
                continue
            asked_at, towers_asked = now, mine
            move = policy.decide(state, options)
            last_signature = signature
            waiting_at = state.elixir if move.detail.get("strategy_choice") in NO_PLAY else None
            if should_stop():
                # Stop was pressed during the request: the answer is discarded, nothing is tapped.
                requests += move.detail.get("requests_made", 0)
                break

            action = "wait"
            strategy = move.detail.get("strategy_choice", "")
            if move.card is not None and move.square is not None:
                play_card(device, screenshot, move.card.slot, move.square)
                if not getattr(device, "dry_run", False):
                    settling = ((state.elixir, tuple(card.name for card in state.hand)), time.time())
                # A spell leaves no troop behind. Everything else puts troops of mine where it was played.
                if not getattr(device, "dry_run", False) and info(move.card.name).kind != "spell":
                    perception.played(move.card.name, move.square.xy)
                plays.append((move.card.name, move.square.name, time.time()))
                action = f"{move.card.name} -> {move.square.name}"
                last_signature = None

            print(
                f"[{state.elapsed_s:5.1f}s] {state.elixir:2d} elixir  {strategy:20s} {action}  ({move.source})"
            )
            entry = {
                "state_elapsed": round(state.elapsed_s),
                "square_xy": move.square.xy if move.square else None,
                "state": asdict(state),
                "options": {
                    option.card.name: [square.name for square in option.squares] for option in options
                },
                "action": action,
                "source": move.source,
                **move.detail,
            }
            # A small picture of the hand as it was read, so any misread can be checked afterwards.
            hand_dir = log_path.with_suffix("")
            hand_dir.mkdir(exist_ok=True)
            strip = to_reference(screenshot)[int(0.82 * 633) :]
            cv2.imwrite(str(hand_dir / f"{decisions:03d}_{round(state.elapsed_s)}s.jpg"), strip)
            log.write(json.dumps(entry) + "\n")
            log.flush()
            if view is not None:
                view.publish(screenshot, state, build_state(state), entry)
            decisions += 1
            requests += move.detail.get("requests_made", 0)
            if max_decisions is not None and decisions >= max_decisions:
                break
            if max_requests is not None and requests >= max_requests:
                print(f"Request budget of {max_requests} reached — stopping.")
                break

    if view is not None:
        view.progress = {"requests": requests, "decisions": decisions, "cards_played": len(plays)}
    print(
        f"Match over — {len(plays)} cards played, {decisions} decisions, {requests} Jev requests. Log: {log_path}"
    )
    return len(plays)
