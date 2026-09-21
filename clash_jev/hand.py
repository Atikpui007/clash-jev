"""Hand reading: which four cards you hold, whether each is playable, and which card comes next.

A card's art is matched against a bank of known cards (`card_shapes.json`, plus cards added with
`clash-jev add-card`). All positions are on the 419x633 reference layout.
"""

import itertools
import json
from pathlib import Path

import cv2
import numpy

from clash_jev.screenmap import ScreenMap
from clash_jev.state import HandCard

CARD_SHAPES = Path(__file__).with_name("card_shapes.json")
EXTRA_CARD_SHAPES = Path(__file__).with_name("extra_card_shapes.json")  # written by `add-card`
# Centre of each hand card, as fractions of the frame.
HAND_TAP_POINTS = ((0.339, 0.886), (0.501, 0.889), (0.649, 0.886), (0.814, 0.889))
# Top-left corner of each hand card and the size of a card, in reference pixels.
SLOTS = ((115, 529), (182, 529), (249, 529), (316, 529))
CARD_WIDTH, CARD_HEIGHT = 54, 66
# The "Next:" thumbnail is a half-size hand card, at this box on the reference layout (x, y, w, h).
_NEXT_BOX = (52, 591, 25, 31)

# Minimum shape-match score in the hand and as the Next thumbnail, and minimum lead over the runner-up.
# The right card scores 0.71+ in the hand and 0.84+ as the Next thumbnail, at least 0.30 ahead.
_HAND_MATCH = 0.55
_NEXT_MATCH = 0.70
_MATCH_MARGIN = 0.15
# A banner ("No card selected") can cover the top of a card. The lower half alone tells cards apart
# less surely, so it is only used when the whole picture is not decisive, and has to be near-perfect.
_LOWER_HALF_MATCH = 0.85
_LOWER_HALF_MARGIN = 0.30
_THUMB = (14, 16)  # width, height of a shape thumbnail
# Fine-detail match, tried first. The right card scores 0.73+ lit, greyed or washed out. A card enlarged
# while it is being dragged scores near 0 here and is left to the shape match.
_DETAIL_SIZE = (28, 32)
_DETAIL_SIGMA = 2.0
_DETAIL_MATCH = 0.45
_EMPTY_TEXTURE = 12.0
_EMPTY_SATURATION = 150.0
# A playable card is in full colour top to bottom: lit cards measure >= 39 mean saturation in their
# weakest band, greyed ones 0. Requiring every band keeps a half-filled card from reading as ready.
_LIT_SATURATION = 15.0
_BANDS = ((4, 18), (18, 32), (32, 46))
_ART = (
    0.15,
    0.09,
    0.85,
    0.73,
)  # the picture inside a card, as fractions of the card: no frame, no cost badge


def _shape(reference: numpy.ndarray, box: tuple[int, int, int, int]) -> numpy.ndarray:
    """A card's picture as a normalised greyscale thumbnail: identical lit or greyed, at any size."""
    x, y, width, height = box
    art = reference[
        y + round(_ART[1] * height) : y + round(_ART[3] * height),
        x + round(_ART[0] * width) : x + round(_ART[2] * width),
    ]
    thumb = cv2.resize(cv2.cvtColor(art, cv2.COLOR_BGR2GRAY), _THUMB, interpolation=cv2.INTER_AREA)
    thumb = thumb.astype(numpy.float32).ravel()
    thumb -= thumb.mean()
    norm = numpy.linalg.norm(thumb)
    return thumb / norm if norm else thumb


def _detail(reference: numpy.ndarray, box: tuple[int, int, int, int]) -> numpy.ndarray:
    """A card's picture reduced to its fine detail: every point compared with its own surroundings, so broad
    light and dark areas drop out. The wipe the game draws over a card you cannot afford is a broad area,
    so the lines of the drawing underneath it survive."""
    x, y, width, height = box
    art = reference[
        y + round(_ART[1] * height) : y + round(_ART[3] * height),
        x + round(_ART[0] * width) : x + round(_ART[2] * width),
    ]
    grey = cv2.resize(cv2.cvtColor(art, cv2.COLOR_BGR2GRAY), _DETAIL_SIZE, interpolation=cv2.INTER_AREA)
    grey = grey.astype(numpy.float32)
    surroundings = cv2.GaussianBlur(grey, (0, 0), _DETAIL_SIGMA)
    spread = numpy.sqrt(cv2.GaussianBlur((grey - surroundings) ** 2, (0, 0), _DETAIL_SIGMA)) + 4.0
    detail = ((grey - surroundings) / spread).ravel()
    detail -= detail.mean()
    norm = numpy.linalg.norm(detail)
    return detail / norm if norm else detail


def _lower_half(shape: numpy.ndarray) -> numpy.ndarray:
    half = shape.reshape(_THUMB[1], _THUMB[0])[_THUMB[1] // 2 :].ravel()
    half = half - half.mean()
    norm = numpy.linalg.norm(half)
    return half / norm if norm else half


def _slot_box(slot: int) -> tuple[int, int, int, int]:
    return (*SLOTS[slot], CARD_WIDTH, CARD_HEIGHT)


def _is_empty(reference: numpy.ndarray, slot: int) -> bool:
    """Between a play and the next card landing, a slot shows a flat, strongly blue placeholder.
    Texture / saturation: placeholder 7 / 239, greyed cards 14-20 / 0, lit cards 41-58 / 80-160."""
    x, y = SLOTS[slot]
    art = reference[y + 6 : y + 48, x + 8 : x + 46]
    flat = float(cv2.cvtColor(art, cv2.COLOR_BGR2GRAY).std()) < _EMPTY_TEXTURE
    return flat and float(cv2.cvtColor(art, cv2.COLOR_BGR2HSV)[..., 1].mean()) > _EMPTY_SATURATION


def _is_lit(reference: numpy.ndarray, slot: int) -> bool:
    x, y = SLOTS[slot]
    saturation = cv2.cvtColor(reference[y : y + 50, x + 8 : x + 46], cv2.COLOR_BGR2HSV)[..., 1]
    return min(float(saturation[top:bottom].mean()) for top, bottom in _BANDS) >= _LIT_SATURATION


class ShapeBank:
    """Known card shapes, as one matrix: a dot product with a card's shape scores it against them all."""

    def __init__(self):
        shapes = json.loads(CARD_SHAPES.read_text())
        if EXTRA_CARD_SHAPES.exists():
            shapes.update(json.loads(EXTRA_CARD_SHAPES.read_text()))
        self.names = list(shapes)
        self.matrix = numpy.array([shapes[name]["shape"] for name in self.names], dtype=numpy.float32)
        self.lower = numpy.stack([_lower_half(shape) for shape in self.matrix])
        self.details = numpy.array([shapes[name]["detail"] for name in self.names], dtype=numpy.float32)

    def match(
        self, shape: numpy.ndarray, lower_half: bool = False, detail: bool = False
    ) -> tuple[str | None, float, float]:
        """(best card, its score, its lead over the runner-up)."""
        if detail:
            scores = self.details @ shape
        else:
            scores = self.lower @ _lower_half(shape) if lower_half else self.matrix @ shape
        order = scores.argsort()[::-1]
        lead = float(scores[order[0]] - scores[order[1]]) if len(order) > 1 else 1.0
        return self.names[order[0]], float(scores[order[0]]), lead


class HandReader:
    """Reads the four hand cards and the Next card. Every name comes from the card's picture, never from
    the deck order."""

    def __init__(self):
        self.bank = ShapeBank()
        self.next_card: str | None = None

    def read(self, frame: numpy.ndarray) -> tuple[HandCard, ...]:
        reference = _reference(frame)
        hand = []
        for slot in range(4):
            if _is_empty(reference, slot):  # the slot is between cards: the new one has not landed yet
                hand.append(HandCard(slot, "unknown", False))
                continue
            name, score, lead = self.bank.match(_detail(reference, _slot_box(slot)), detail=True)
            known = score >= _DETAIL_MATCH and lead >= _MATCH_MARGIN
            shape = _shape(reference, _slot_box(slot))
            if not known:
                name, score, lead = self.bank.match(shape)
                known = score >= _HAND_MATCH and lead >= _MATCH_MARGIN
            if not known:
                name, score, lead = self.bank.match(shape, lower_half=True)
                known = score >= _LOWER_HALF_MATCH and lead >= _LOWER_HALF_MARGIN
            hand.append(HandCard(slot, name if known else "unknown", _is_lit(reference, slot)))
        self.next_card = self._read_next(reference)
        return tuple(hand)

    def _read_next(self, reference: numpy.ndarray) -> str | None:
        """The thumbnail sits a pixel or two differently from frame to frame, so a few nearby boxes are
        tried and the best score wins."""
        x, y, width, _ = _NEXT_BOX
        best: tuple[float, str | None, float] = (0.0, None, 0.0)
        for dx, dy, dw in itertools.product((-1, 0, 1), (-2, 0, 2), (0, 1, 2)):
            box = (x + dx, y + dy, width + dw, round((width + dw) * CARD_HEIGHT / CARD_WIDTH))
            if box[1] + box[3] > reference.shape[0]:
                continue
            name, score, lead = self.bank.match(_shape(reference, box))
            if score > best[0]:
                best = (score, name, lead)
        score, name, lead = best
        return name if score >= _NEXT_MATCH and lead >= _MATCH_MARGIN else None


def read_hand(frame: numpy.ndarray) -> tuple[HandCard, ...]:
    """One-off read (snap, add-card checks)."""
    return HandReader().read(frame)


def _reference(frame: numpy.ndarray) -> numpy.ndarray:
    return ScreenMap.for_frame(frame).to_reference(frame)


def add_card(frame: numpy.ndarray, slot: int, name: str) -> None:
    """Teach the reader a card it does not know, from the card sitting in `slot` right now."""
    reference = _reference(frame)
    saved = json.loads(EXTRA_CARD_SHAPES.read_text()) if EXTRA_CARD_SHAPES.exists() else {}
    saved[name] = {
        "shape": [round(float(value), 4) for value in _shape(reference, _slot_box(slot))],
        "detail": [round(float(value), 4) for value in _detail(reference, _slot_box(slot))],
    }
    EXTRA_CARD_SHAPES.write_text(json.dumps(saved, separators=(",", ":")))
