"""Turn a recorded run into a replay someone else can watch:  clash-jev publish runs/<run>-jev.jsonl --to DIR

Writes DIR/<run>/video.mp4 and DIR/<run>/replay.json, and lists the run in DIR/index.json. The opponent's
name is blurred wherever the game shows it, because an opponent is a real person who did not ask to be shown.
"""

import json
from pathlib import Path

import cv2
import numpy

# The banner at the top left of the arena with the opponent's name and clan, as fractions of the device
# frame. The results screen shows the name again, on a banner found by its colour (_opponent_banner).
_NAME_BANNER = (0.0, 0.0, 0.47, 0.062)  # x0, y0, x1, y1
_AFTER_LAST_DECISION_S = 2.0
_PER_DECISION = (
    "state_elapsed", "action", "note", "source", "latency_ms", "step_ms", "requests_made", "square_xy",
    "strategy_choice", "strategy_probabilities", "card_choice", "card_probabilities", "square_choice",
    "square_probabilities",
)  # fmt: skip


def _in_battle(row: dict) -> bool:
    """False for a read of the results screen: few cards can be made out on it, or the same card is read
    in two slots, which a real hand never holds."""
    named = [card["name"] for card in row["state"]["hand"] if card["name"] != "unknown"]
    return len(named) >= 2 and len(set(named)) == len(named)


def _crowns(rows: list[dict]) -> tuple[int, int]:
    """(towers I destroyed, towers I lost), from the last reading taken while the match was still on."""
    towers = rows[-1]["state"]["towers"]
    return (
        sum(towers[name] == 0 for name in ("enemy_left", "enemy_right", "enemy_king")),
        sum(towers[name] == 0 for name in ("my_left", "my_right", "my_king")),
    )


def _opponent_banner(image: numpy.ndarray) -> tuple[int, int, int, int] | None:
    """x, y, width, height of the part of the results screen that holds the opponent's name.

    The name sits on a wide crimson banner that slides into place, so the banner is found by its colour."""
    height, width = image.shape[:2]
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    crimson = (hsv[..., 0] >= 160) & (hsv[..., 0] <= 178) & (hsv[..., 1] >= 140) & (hsv[..., 2] >= 90)
    joined = cv2.morphologyEx(crimson.astype(numpy.uint8), cv2.MORPH_CLOSE, numpy.ones((9, 25), numpy.uint8))
    _, _, boxes, _ = cv2.connectedComponentsWithStats(joined)
    for x, y, wide, tall, _ in boxes[1:]:
        if wide >= 0.5 * width and tall >= 0.04 * height:
            crowns = int(tall * 0.4) if tall > 0.1 * height else 0  # the crowns above the banner stay visible
            return int(x), int(y + crowns), int(wide), int(tall - crowns)
    return None


def _results_crowns(image: numpy.ndarray) -> tuple[int, int] | None:
    """(my crowns, the opponent's), counted on the results screen. None when this is not that screen.

    The opponent's crowns sit on their banner and mine sit just under it. Won crowns are gold."""
    banner = _opponent_banner(image)
    if banner is None:
        return None
    height = image.shape[0]
    _, top, _, tall = banner
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    gold = (hsv[..., 0] >= 12) & (hsv[..., 0] <= 32) & (hsv[..., 1] >= 150) & (hsv[..., 2] >= 170)
    joined = cv2.morphologyEx(gold.astype(numpy.uint8), cv2.MORPH_CLOSE, numpy.ones((7, 7), numpy.uint8))
    _, _, blobs, _ = cv2.connectedComponentsWithStats(joined)
    crowns = [
        (y, tall_) for _, y, wide, tall_, area in blobs[1:] if area >= 2000 and wide < 0.3 * image.shape[1]
    ]
    theirs = sum(top - 0.15 * height <= y and y + tall_ <= top + 0.4 * tall for y, tall_ in crowns)
    mine = sum(top + tall <= y <= top + tall + 0.2 * height for y, tall_ in crowns)
    return int(mine), int(theirs)


def _video(source: Path, target: Path, battle_until_s: float) -> tuple[float, tuple[int, int] | None]:
    """The whole recording, results screen included, with the opponent's name made unreadable throughout."""
    import av

    with (
        av.open(str(source)) as recorded,
        av.open(str(target), "w", options={"movflags": "faststart"}) as output,
    ):
        stream_in = recorded.streams.video[0]
        rate = stream_in.average_rate or 10
        stream = output.add_stream("libx264", rate=rate)
        stream.width, stream.height, stream.pix_fmt = stream_in.width, stream_in.height, "yuv420p"
        stream.options = {"crf": "26", "preset": "medium"}
        last, results_banner, crowns = 0.0, None, None
        for index, picture in enumerate(recorded.decode(stream_in)):
            when = float(picture.pts * stream_in.time_base)
            image = picture.to_ndarray(format="bgr24")
            if when > battle_until_s:
                # Once the banner has shown up it stays covered, also on a frame where it could not be found.
                results_banner = _opponent_banner(image) or results_banner
                crowns = _results_crowns(image) or crowns  # read before the name is covered
                if results_banner:
                    x, y, wide, tall = results_banner
                    name = image[y : y + tall, x : x + wide]
                    name[:] = cv2.GaussianBlur(name, (0, 0), 12)
            height, width = image.shape[:2]
            x0, y0, x1, y1 = _NAME_BANNER
            banner = image[int(y0 * height) : int(y1 * height), int(x0 * width) : int(x1 * width)]
            banner[:] = cv2.GaussianBlur(banner, (0, 0), 9)  # unreadable, without a black hole in the picture
            frame = av.VideoFrame.from_ndarray(image, format="bgr24")
            frame.pts = index
            for packet in stream.encode(frame):
                output.mux(packet)
            last = when
        for packet in stream.encode():
            output.mux(packet)
    return last, crowns


def publish(log: Path, folder: Path, title: str | None = None) -> dict:
    rows = [json.loads(line) for line in log.read_text().splitlines() if line.strip()]
    rows = [row for row in rows if _in_battle(row)]
    if not rows:
        raise SystemExit(f"{log} holds no decision made during a match.")
    run = log.stem.removesuffix("-jev")
    target = folder / run
    target.mkdir(parents=True, exist_ok=True)

    sent = [row["request"]["state"] for row in rows if "request" in row]
    briefing = sent[0].get("game") if sent else None
    questions: dict[str, str] = {}
    decisions = []
    for row in rows:
        decision = {key: row[key] for key in _PER_DECISION if key in row}
        request = row.get("request", {})
        decision["state"] = {key: value for key, value in request.get("state", {}).items() if key != "game"}
        decision["options"] = {}
        for step, question in request.get("questions", {}).items():
            questions.setdefault(step, question.get("instructions", ""))
            decision["options"][step] = question.get("options", {})
        decision["units"] = [
            {key: unit.get(key) for key in ("owner", "x", "y", "name", "health")}
            for unit in row["state"]["units"]
        ]
        decisions.append(decision)

    seconds = rows[-1]["state_elapsed"] + _AFTER_LAST_DECISION_S
    video = log.with_suffix(".mp4")
    shown = None
    if video.exists():
        seconds, shown = _video(video, target / "video.mp4", seconds)
    # The score on the results screen is the game's own count. Tower readings stand in when it is missing.
    won, lost = shown or _crowns(rows)
    plays = [decision for decision in decisions if " -> " in str(decision.get("action"))]
    summary = {
        "id": run,
        "title": title or f"Match {run[:8]} {run[9:11]}:{run[11:13]}",
        "seconds": round(seconds, 1),
        "decisions": len(decisions),
        "plays": len(plays),
        "requests": sum(decision.get("requests_made", 0) for decision in decisions),
        "towers_destroyed": won,
        "towers_lost": lost,
        "has_video": video.exists(),
    }
    replay = {"summary": summary, "briefing": briefing, "questions": questions, "decisions": decisions}
    (target / "replay.json").write_text(json.dumps(replay, separators=(",", ":")))

    index_file = folder / "index.json"
    index = json.loads(index_file.read_text()) if index_file.exists() else []
    index = sorted(
        [entry for entry in index if entry["id"] != run] + [summary], key=lambda entry: entry["id"]
    )
    index_file.write_text(json.dumps(index, indent=1))
    return summary
