"""clash-jev serve | snap | play | add-card | label | train | publish"""

import argparse
import os
import sys
import time
from pathlib import Path

import cv2

from clash_jev.device import AdbDevice, ImageDevice, StreamDevice
from clash_jev.hand import HAND_TAP_POINTS
from clash_jev.moves import ALL_SQUARES, get_valid_moves
from clash_jev.perception import Perception
from clash_jev.policy import BaselinePolicy, JevPolicy
from clash_jev.runner import play_match
from clash_jev.screenmap import ScreenMap


def snap(frame, out: Path) -> None:
    """Draw every reading and tap point on the frame, and print the state and valid moves."""
    perception = Perception()
    state = perception.extract_state(frame)
    screen = ScreenMap.for_frame(frame)
    print(
        f"device screen {screen.width}x{screen.height}: "
        + ("calibrated" if screen.calibrated else "NOT calibrated — using the nearest known shape")
    )
    # Draw on the reference layout, where every probe is defined; the taps are mapped back to the device.
    frame = cv2.resize(screen.to_reference(frame), (838, 1266), interpolation=cv2.INTER_LINEAR)
    height, width = frame.shape[:2]

    def point(xy):
        return int(xy[0] * width), int(xy[1] * height)

    lay = perception.layout
    for x in lay.elixir_x:
        cv2.circle(frame, point((x, lay.elixir_y)), 3, (0, 255, 255), 1)
    for _, (x0, y0, x1, y1) in lay.tower_bars:
        cv2.rectangle(frame, point((x0, y0)), point((x1, y1)), (0, 255, 255), 1)
    for xy in HAND_TAP_POINTS:
        cv2.drawMarker(frame, point(xy), (255, 0, 0), cv2.MARKER_TILTED_CROSS, 10, 2)
    for unit in state.units:
        colour = (0, 0, 255) if unit.owner == "enemy" else (255, 128, 0)
        cv2.circle(frame, point((unit.x, unit.y)), 12, colour, 2)
    for square in ALL_SQUARES.values():
        cv2.drawMarker(frame, point(square.xy), (255, 255, 255), cv2.MARKER_CROSS, 10, 1)
        cv2.putText(frame, square.name, point(square.xy), cv2.FONT_HERSHEY_SIMPLEX, 0.3, (255, 255, 255), 1)
    cv2.imwrite(str(out), frame)

    print(f"{width}x{height} -> {out}")
    print(f"elixir: {state.elixir}   next card: {state.next_card}")
    print("hand:", ", ".join(f"{card.name}{'' if card.ready else ' (not ready)'}" for card in state.hand))
    for card in state.hand:
        if card.name == "unknown":
            print(
                f"  slot {card.slot + 1} is not recognised — teach it: clash-jev add-card <card_id> --slot {card.slot + 1}"
            )
    print("left :", state.left)
    print("right:", state.right)
    print("towers:", state.towers)
    for option in get_valid_moves(state):
        print(f"  can play {option.card.name}: {', '.join(square.name for square in option.squares)}")
    taps = {name: screen.to_device(ALL_SQUARES[name].xy) for name in ("left_bridge", "right_tower_front")}
    print("device tap points:", taps, "| hand slot 1:", screen.to_device(HAND_TAP_POINTS[0]))


def main() -> None:
    parser = argparse.ArgumentParser(prog="clash-jev")
    parser.add_argument("command", choices=["serve", "snap", "play", "add-card", "label", "train", "publish"])
    parser.add_argument(
        "name", nargs="?", help="add-card: the card id, e.g. evo_valkyrie; publish: the run's .jsonl"
    )
    parser.add_argument("--slot", type=int, help="add-card: hand slot 1-4 holding that card")
    parser.add_argument("--serial", help="adb device serial (adb devices)")
    parser.add_argument("--image", help="use this screenshot file instead of the live emulator screen")
    parser.add_argument(
        "--view",
        action="store_true",
        help="dock a native panel beside the emulator: what the bot read, what it asked, what Jev answered",
    )
    parser.add_argument("--web", action="store_true", help="serve the same information as a browser page")
    parser.add_argument(
        "--env-file", default=".env", help="file to read TYPESAFE_API_KEY from if it is not set"
    )
    parser.add_argument("--policy", choices=["jev", "baseline"], default="jev")
    parser.add_argument("--dry-run", action="store_true", help="decide and log, but never tap")
    parser.add_argument("--matches", type=int, default=1)
    parser.add_argument(
        "--every", type=float, default=1.0, help="seconds between snapshots sent to Jev (default 1)"
    )
    parser.add_argument(
        "--arena",
        type=int,
        help="the arena you play in (0 = training camp): enemy troops are only named as cards unlocked by then",
    )
    parser.add_argument(
        "--collect",
        metavar="DIR",
        help="save a picture of every enemy troop seen during battles into DIR, filed by the name it was given",
    )
    parser.add_argument(
        "--to", default="web/public/replays", help="publish: the folder the replay site reads"
    )
    parser.add_argument("--title", help="publish: the name shown for the run")
    parser.add_argument("--max-requests", type=int, help="stop the run once this many Jev requests were made")
    args = parser.parse_args()
    if args.collect:
        os.environ["CLASH_JEV_COLLECT"] = str(Path(args.collect).resolve())
    if args.arena is not None:
        os.environ["CLASH_JEV_ARENA"] = str(args.arena)

    if args.command == "label":
        from clash_jev.label import serve

        if not args.collect:
            sys.exit(
                "usage: clash-jev label --collect DIR [--arena N]   (DIR is where --collect saved the pictures)"
            )
        serve(Path(args.collect), args.arena)
        return

    if args.command == "publish":
        from clash_jev.publish import publish

        if not args.name:
            sys.exit("usage: clash-jev publish runs/<run>-jev.jsonl [--to web/public/replays] [--title TEXT]")
        print(publish(Path(args.name), Path(args.to), args.title))
        return

    if args.command == "train":
        from clash_jev.train import train

        if not args.collect:
            sys.exit("usage: clash-jev train --collect DIR   (DIR holds the pictures and the labels.json)")
        train(Path(args.collect))
        return

    if args.command == "add-card":
        from clash_jev.cards import known
        from clash_jev.hand import add_card

        if not args.name or args.slot not in (1, 2, 3, 4):
            sys.exit(
                "usage: clash-jev add-card <card_id> --slot <1-4>   (with that card visible in your hand)"
            )
        if not known(args.name):
            sys.exit(f"'{args.name}' has no entry in clash_jev/cards.py — add its facts there first.")
        frame = cv2.imread(args.image) if args.image else AdbDevice(args.serial).frame()
        add_card(frame, args.slot - 1, args.name)
        print(f"Learned {args.name} from slot {args.slot}.")
        return

    if args.command == "snap":
        frame = cv2.imread(args.image) if args.image else AdbDevice(args.serial).frame()
        if frame is None:
            sys.exit(f"Could not read {args.image}")
        snap(frame, Path("snap.png"))
        return

    env_file = Path(args.env_file)
    if not os.environ.get("TYPESAFE_API_KEY") and env_file.exists():
        for line in env_file.read_text().splitlines():
            key, _, value = line.removeprefix("export ").partition("=")
            if key.strip() == "TYPESAFE_API_KEY":
                os.environ["TYPESAFE_API_KEY"] = value.strip().strip("\"'")
    if args.policy == "jev" and not os.environ.get("TYPESAFE_API_KEY"):
        sys.exit("TYPESAFE_API_KEY is not set.")

    if args.command == "serve":
        import subprocess
        import webbrowser

        if os.environ.get("CLASH_JEV_WORKER") != "1":
            # Supervisor: the page's server runs in a child process, so a native crash (a GPU or video
            # library segfault cannot be caught in Python) costs a one-second restart, not the session.
            print(
                "Control page: http://127.0.0.1:8765 — Start and Stop runs from the page. Ctrl+C here to quit."
            )
            opened = False
            try:
                while True:
                    worker = subprocess.Popen(
                        [sys.executable, "-m", "clash_jev.cli", *sys.argv[1:]],
                        env={**os.environ, "CLASH_JEV_WORKER": "1"},
                    )
                    if not opened:
                        time.sleep(4)
                        webbrowser.open("http://127.0.0.1:8765")
                        opened = True
                    code = worker.wait()
                    print(f"The bot process ended (exit code {code}) — restarting it.")
                    time.sleep(1)
            except KeyboardInterrupt:
                worker.terminate()
            return

        from clash_jev.control import Controller
        from clash_jev.view import LiveView

        Controller(StreamDevice(args.serial), LiveView())
        while True:
            time.sleep(3600)

    if args.image:
        device = ImageDevice(args.image)
    else:
        device = StreamDevice(args.serial, dry_run=args.dry_run)
    view = None
    if args.web:
        import webbrowser

        from clash_jev.view import LiveView

        view = LiveView()
        webbrowser.open(f"http://127.0.0.1:{view.port}")
    policy = JevPolicy() if args.policy == "jev" else BaselinePolicy()

    def matches(view) -> None:
        for _ in range(1 if args.image else args.matches):
            log_path = Path("runs") / f"{time.strftime('%Y%m%d-%H%M%S')}-{args.policy}.jsonl"
            play_match(
                device,
                policy,
                log_path,
                view,
                max_decisions=1 if args.image else None,
                max_requests=args.max_requests,
                every=args.every,
            )

    if args.view:
        import threading

        from clash_jev.panel import Panel

        panel = Panel(show_screen=bool(args.image))
        panel.run(threading.Thread(target=matches, args=(panel,), daemon=True))
    else:
        matches(view)
        if view is not None:
            print("Run finished. The page stays up with the last decisions — Ctrl+C to close.")
            try:
                while True:
                    time.sleep(3600)
            except KeyboardInterrupt:
                pass


if __name__ == "__main__":
    main()
