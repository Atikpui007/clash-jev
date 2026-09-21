"""Map a device's real screen onto the 419x633 reference layout, and back.

Every reading (card shapes, elixir pips, tower bars, squares) is defined on the reference layout. The game
scales the arena and the bottom bar as two separate blocks, so each block has its own affine map per screen
shape. All maps work in "g space": the device frame scaled to 419 px wide, whatever height that gives.
"""

from dataclasses import dataclass

import cv2
import numpy

REFERENCE = (419, 633)  # width, height
SPLIT_Y = 505  # reference row where the arena ends and the bottom bar (hand, elixir) begins
_CENTRE_X = 209.5


@dataclass(frozen=True)
class Calibration:
    arena_scale_x: float = 1.0  # g = centre + scale * (ref - centre)
    arena_scale_y: float = 1.0  # g = scale * ref + arena_offset_y
    arena_offset_y: float = 0.0
    bottom_scale: float = 1.0  # ref = scale * g, anchored at the bottom-centre of the screen
    bottom_dx: float = 0.0
    bottom_dy: float = 0.0


# Keyed by screen shape (width / height, 3 decimals). Shapes not listed fall back to the nearest.
CALIBRATIONS: dict[float, Calibration] = {
    0.662: Calibration(),  # 419x633 and exact multiples: the reference itself
    # A 1440x2304 tablet. Arena: enemy bars y 95->101, own bars 393->415, river 276->292,
    # bar centres x 122.5/308.5 -> 116.5/314.5. Bottom bar: best card fit over 8 cards.
    0.625: Calibration(1.0645, 1.0537, 0.9, 0.94, 0.0, -1.0),
}


class ScreenMap:
    def __init__(self, width: int, height: int):
        self.width, self.height = width, height
        self.g_height = round(height * REFERENCE[0] / width)
        shape = round(width / height, 3)
        self.calibrated = shape in CALIBRATIONS
        self.calibration = CALIBRATIONS[min(CALIBRATIONS, key=lambda known: abs(known - shape))]
        c, h = self.calibration, self.g_height
        # g -> reference, one matrix per block
        self._arena = numpy.float32(
            [
                [1 / c.arena_scale_x, 0, _CENTRE_X * (1 - 1 / c.arena_scale_x)],
                [0, 1 / c.arena_scale_y, -c.arena_offset_y / c.arena_scale_y],
            ]
        )
        self._bottom = numpy.float32(
            [
                [c.bottom_scale, 0, (1 - c.bottom_scale) * _CENTRE_X + c.bottom_dx],
                [0, c.bottom_scale, (1 - c.bottom_scale) * h + c.bottom_dy - (h - REFERENCE[1])],
            ]
        )

    @classmethod
    def for_frame(cls, frame: numpy.ndarray) -> "ScreenMap":
        return cls(frame.shape[1], frame.shape[0])

    def to_reference(self, frame: numpy.ndarray, scale: int = 1) -> numpy.ndarray:
        """The device frame redrawn on the reference layout. `scale` draws the same layout with that
        many times the pixels, for readings that need detail the device has and 419 columns lose (a
        troop's level badge is 10 px tall at reference size)."""
        size = (REFERENCE[0] * scale, REFERENCE[1] * scale)
        if frame.shape[1::-1] == size:
            return frame
        if frame.shape[1::-1] == REFERENCE:
            return cv2.resize(frame, size, interpolation=cv2.INTER_LINEAR)
        shrinking = frame.shape[1] > size[0]
        g = cv2.resize(
            frame,
            (size[0], self.g_height * scale),
            interpolation=cv2.INTER_AREA if shrinking else cv2.INTER_LINEAR,
        )
        grow = numpy.float32(
            [[1, 1, scale], [1, 1, scale]]
        )  # a larger drawing moves the offsets, not the ratios
        reference = cv2.warpAffine(
            g, self._arena * grow, size, flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE
        )
        bottom = cv2.warpAffine(
            g, self._bottom * grow, size, flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE
        )
        reference[SPLIT_Y * scale :] = bottom[SPLIT_Y * scale :]
        return reference

    def to_device(self, xy: tuple[float, float]) -> tuple[int, int]:
        """A point given as reference fractions -> the pixel to tap on the real screen."""
        x, y = xy[0] * REFERENCE[0], xy[1] * REFERENCE[1]
        if (self.width, self.height) == REFERENCE:
            return int(x), int(y)
        matrix = self._bottom if y >= SPLIT_Y else self._arena
        gx = (x - matrix[0, 2]) / matrix[0, 0]
        gy = (y - matrix[1, 2]) / matrix[1, 1]
        scale = self.width / REFERENCE[0]
        return int(gx * scale), int(gy * scale)
