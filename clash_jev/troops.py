"""Name the troops on the board with the project's own small network.

A troop is found by its level badge (units.py). The picture right under the badge is cut from the frame and
the network says which card it is. The network runs through OpenCV. troop_model.json lists the cards it knows.
"""

import json
from dataclasses import replace
from pathlib import Path

import cv2
import numpy

from clash_jev.units import Unit

MODEL = Path(__file__).with_name("troop_model.onnx")
MODEL_FACTS = Path(__file__).with_name("troop_model.json")

# The picture around a troop, as fractions of the frame, measured from its level badge. A troop stands just
# below its badge, and the largest (a giant) are about this wide. Collected pictures are cut the same way.
LEFT, RIGHT, ABOVE, BELOW = 0.09, 0.09, 0.015, 0.105
# The part of that picture the network looks at: the troop itself, without most of its neighbours.
LOOK_AT = (0.25, 0.75, 0.08, 0.78)  # x0, x1, y0, y1 of the picture
SIZE = 96
_MEAN = numpy.array([0.406, 0.456, 0.485], numpy.float32)  # blue, green, red
_STD = numpy.array([0.225, 0.224, 0.229], numpy.float32)
MIN_CONFIDENCE = 0.4  # below this the troop stays unnamed rather than being given a guess


def troop_picture(frame: numpy.ndarray, x: float, y: float) -> numpy.ndarray:
    """The picture of the troop whose badge is at (x, y), cut from a frame drawn on the reference layout."""
    height, width = frame.shape[:2]
    x0, x1 = int((x - LEFT) * width), int((x + RIGHT) * width)
    y0, y1 = int((y - ABOVE) * height), int((y + BELOW) * height)
    return frame[max(0, y0) : y1, max(0, x0) : x1]


def network_input(picture: numpy.ndarray) -> numpy.ndarray:
    """One troop picture as the network reads it: cropped to the troop, 96x96, normalised, channels first."""
    height, width = picture.shape[:2]
    x0, x1, y0, y1 = LOOK_AT
    looked_at = picture[int(y0 * height) : int(y1 * height), int(x0 * width) : int(x1 * width)]
    small = cv2.resize(looked_at, (SIZE, SIZE), interpolation=cv2.INTER_AREA).astype(numpy.float32) / 255
    return ((small - _MEAN) / _STD).transpose(2, 0, 1)


class TroopClassifier:
    def __init__(self, arena: int | None = None):
        self.cards: list[str] = json.loads(MODEL_FACTS.read_text())["cards"]
        self._network = cv2.dnn.readNetFromONNX(str(MODEL))
        self._allowed = numpy.ones(len(self.cards), bool)
        if arena is not None:  # an opponent in this arena cannot own a card that unlocks later
            from clash_jev.cards import unlocked_by

            self._allowed = numpy.array([card in unlocked_by(arena) for card in self.cards])

    @staticmethod
    def available() -> bool:
        return MODEL.exists() and MODEL_FACTS.exists()

    def name(self, pictures: list[numpy.ndarray]) -> list[tuple[str, float]]:
        """(card, confidence) for each troop picture."""
        if not pictures:
            return []
        self._network.setInput(numpy.stack([network_input(picture) for picture in pictures]))
        scores = self._network.forward().astype(numpy.float64)
        scores = numpy.exp(scores - scores.max(axis=1, keepdims=True)) * self._allowed
        scores /= scores.sum(axis=1, keepdims=True)
        return [(self.cards[row.argmax()], float(row.max())) for row in scores]

    def name_units(self, frame: numpy.ndarray, units: tuple[Unit, ...]) -> tuple[Unit, ...]:
        """Name the troops of both sides. A card's art is the same for both, only the colours differ."""
        pictures = [troop_picture(frame, unit.x, unit.y) for unit in units]
        usable = [index for index, picture in enumerate(pictures) if picture.size]
        named = list(units)
        for index, (card, confidence) in zip(usable, self.name([pictures[index] for index in usable])):
            if confidence >= MIN_CONFIDENCE:
                named[index] = replace(named[index], name=card, confidence=round(confidence, 2))
        return tuple(named)
