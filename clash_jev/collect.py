"""Collect pictures of troops from your own matches, to train the troop network on.

With $CLASH_JEV_COLLECT (set by --collect DIR) every snapshot that shows a battle saves one small picture
per troop. DIR/enemy/<name>/ is filed by the name the troop network gave, which is a guess. DIR/mine/<card>/
is filed by the card the bot played at that spot, or "unnamed" for troops played by hand.
"""

import os
import time
from collections import Counter
from pathlib import Path

import cv2
import numpy

from clash_jev.state import HandCard
from clash_jev.troops import troop_picture
from clash_jev.units import Unit

collected: Counter[str] = Counter()  # frames and pictures saved by this process, for the page to show
_FRAME_EVERY_S = 1  # a full frame beside the troop pictures: what a troop finder can later be trained on
_last_frame_at = 0


def collect_dir() -> Path | None:
    value = os.environ.get("CLASH_JEV_COLLECT")
    return Path(value) if value else None


def save_troops(frame: numpy.ndarray, hand: tuple[HandCard, ...], units: tuple[Unit, ...]) -> int:
    """Saves nothing unless a hand is on screen: a menu has badge-coloured shapes of its own."""
    target = collect_dir()
    if target is None or sum(card.name != "unknown" for card in hand) < 3:
        return 0
    stamp = int(time.time() * 1000)
    global _last_frame_at
    if stamp - _last_frame_at >= _FRAME_EVERY_S * 1000:
        _last_frame_at = stamp
        (target / "frames").mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(target / "frames" / f"{stamp}.jpg"), frame)
        collected["frames"] += 1
    saved = 0
    for unit in units:
        if unit.unseen_for_s > 0:
            continue  # only remembered, not seen: the spot may show nothing but the splash where it died
        picture = troop_picture(frame, unit.x, unit.y)
        if picture.size == 0:
            continue
        # Enemy troops are filed by what the troop network called them, mine by the card played there.
        label = unit.name if unit.owner == "enemy" else unit.played_as
        folder = target / unit.owner / (label or "unnamed")
        folder.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(folder / f"{stamp}_{round(unit.x * 1000)}_{round(unit.y * 1000)}.jpg"), picture)
        saved += 1
        collected["pictures"] += 1
    return saved
