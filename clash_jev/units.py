"""Find troops on the arena from their level badges.

Every troop carries a small square level badge, crimson for the enemy and blue for you, with its health
bar attached on the right once it has taken damage. The badge colour gives the owner.
"""

from dataclasses import dataclass

import cv2
import numpy

REFERENCE_WIDTH = 419  # badge sizes below are in pixels at this frame width

# OpenCV hue (0-179) of the badge border, fill and bar for each side.
_TEAM_HUES = {"enemy": (167, 175), "mine": (98, 111)}
_MIN_SATURATION = 100
_BADGE_SIDE = (7, 13)  # badge height range, px at reference width
_MIN_DIGIT_PIXELS = 6  # white level digits inside the badge, px at reference size
_MIN_BADGE_FILL = 0.6  # how much of the square is badge colour or digit


@dataclass(frozen=True)
class Unit:
    owner: str  # "enemy" | "mine"
    x: float  # badge position as a fraction of the frame; the troop stands just below it
    y: float
    health: float | None  # bar fill 0-1, None while undamaged (no bar is drawn)
    name: str | None = None  # card id, when the troop network knows the card (troops.py)
    confidence: float | None = None  # how sure the network was of `name` in this one read
    seen_for_s: float | None = None  # how long this troop has been followed (tracks.py)
    # The card of mine that was played where this troop appeared. Only a label for collected pictures
    # (collect.py). It is never sent.
    played_as: str | None = None
    unseen_for_s: float = (
        0.0  # > 0 when the troop was not seen in this read and is only being remembered (tracks.py)
    )


def _health(hsv: numpy.ndarray, x: int, y: int, width: int, height: int, side: int) -> float | None:
    """The bar is the part of the component to the right of the square badge."""
    bar_width = width - side
    if bar_width < side // 2:
        return None
    row = hsv[y + height // 2, x + side : x + width]
    filled = int((row[:, 2] >= 235).sum())  # the lit part; the emptied part is dark
    return round(float(filled / bar_width), 2)


def find_units(
    frame: numpy.ndarray, ignore: list[tuple[float, float, float, float]] = (), scale: float | None = None
) -> list[Unit]:
    """`ignore` holds (x0, y0, x1, y1) fractions to skip: towers wear the same colours."""
    frame_height, frame_width = frame.shape[:2]
    if scale is None:  # a whole frame; a cut-out of one says how much larger than the reference it was drawn
        scale = frame_width / REFERENCE_WIDTH
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    hue, saturation, value = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    white = (saturation < 40) & (value > 235)
    # The digit's dark outline cuts gaps into the badge. A brush that grows with the picture closes them.
    brush = max(3, round(1.5 * scale) * 2 + 1)
    kernel = numpy.ones((brush, brush), numpy.uint8)

    units = []
    for owner, (low, high) in _TEAM_HUES.items():
        team = (hue >= low) & (hue <= high)
        # Digits are white but keep the badge's hue, so the badge stays one solid block.
        mask = (team & ((saturation >= _MIN_SATURATION) | white)).astype(numpy.uint8)
        for x0, y0, x1, y1 in ignore:
            mask[
                int(y0 * frame_height) : int(y1 * frame_height), int(x0 * frame_width) : int(x1 * frame_width)
            ] = 0
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        _, _, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
        for x, y, width, height, _area in stats[1:]:
            # The badge is a square at the top-left of its shape. A health bar makes the shape wider than that
            # square; a troop in the same colour right under the badge (an archer's hair) makes it taller.
            side = min(width, height)
            if not (_BADGE_SIDE[0] * scale <= side <= _BADGE_SIDE[1] * scale):
                continue
            if height > side * 2.5:  # far too tall to be a badge with something under it: a tower, a banner
                continue
            badge = slice(y, y + side), slice(x, x + side)
            if white[badge].sum() < _MIN_DIGIT_PIXELS * scale or mask[badge].mean() < _MIN_BADGE_FILL:
                continue
            height = side
            units.append(
                Unit(
                    owner,
                    round(float(x + side / 2) / frame_width, 3),
                    round(float(y + side / 2) / frame_height, 3),
                    _health(hsv, x, y, width, height, side),
                )
            )
    return units
