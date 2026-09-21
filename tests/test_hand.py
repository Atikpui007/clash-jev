"""The hand reader on real tablet frames: lit cards, greyed cards and the Next card."""

from pathlib import Path

import cv2
import numpy
import pytest

from clash_jev.hand import SLOTS, HandReader
from clash_jev.screenmap import ScreenMap

FIXTURES = Path(__file__).parent / "fixtures"
LIT = FIXTURES / "tablet_hand_lit.png"  # minions, arrows, mini pekka, knight, all affordable. Next: musketeer
GREY = FIXTURES / "tablet_hand_grey.png"  # the same hand at 0 elixir: every card drawn grey


def _names(hand):
    return [(card.name, card.ready) for card in hand]


def test_greyed_cards_keep_their_names_and_read_as_not_ready():
    reader = HandReader()
    assert _names(reader.read(cv2.imread(str(LIT)))) == [
        ("minions", True),
        ("arrows", True),
        ("mini_pekka", True),
        ("knight", True),
    ]
    assert reader.next_card == "musketeer"
    assert _names(reader.read(cv2.imread(str(GREY)))) == [
        ("minions", False),
        ("arrows", False),
        ("mini_pekka", False),
        ("knight", False),
    ]


def test_a_half_filled_card_is_not_ready_and_still_named():
    """The game fills an unaffordable card with colour bottom-up; that must not read as playable or unknown."""
    lit, grey = cv2.imread(str(LIT)), cv2.imread(str(GREY))
    screen = ScreenMap.for_frame(lit)
    x, y = screen.to_device((SLOTS[0][0] / 419, SLOTS[0][1] / 633))
    _, bottom = screen.to_device((0, (SLOTS[0][1] + 66) / 633))
    right, _ = screen.to_device(((SLOTS[0][0] + 54) / 419, 0))
    half = grey.copy()
    middle = (y + bottom) // 2
    half[middle:bottom, x:right] = lit[middle:bottom, x:right]

    reader = HandReader()
    reader.read(lit)
    minions = reader.read(half)[0]
    assert (minions.name, minions.ready) == ("minions", False)


def _reference_from_strip(path: Path):
    """The run logs save the bottom strip of the reference layout; put it back where it belongs."""

    strip = cv2.imread(str(path))
    canvas = numpy.zeros((633, 419, 3), numpy.uint8)
    canvas[633 - strip.shape[0] :] = strip
    return canvas


def test_a_real_sequence_with_plays_an_empty_slot_a_banner_and_never_lit_cards():
    """Nine consecutive reads from a recorded match."""
    reader = HandReader()
    reads = {}
    for path in sorted((FIXTURES / "hand_sequence").glob("*.jpg")):
        hand = reader.read(_reference_from_strip(path))
        reads[path.name] = ([card.name for card in hand], [card.ready for card in hand], reader.next_card)

    assert reads["000_0s.jpg"][0] == ["giant", "knight", "archers", "minions"]
    assert reads["000_0s.jpg"][2] == "arrows"
    assert reads["003_5s.jpg"][0] == ["arrows", "knight", "archers", "minions"]  # arrows arrived from Next
    assert reads["003_5s.jpg"][2] == "fireball"
    # minions was just played: its slot is empty until the next card lands.
    assert reads["007_11s.jpg"][0] == ["arrows", "knight", "archers", "unknown"]
    # A red "No card selected" banner covers the top of slots 1-2; slots 3-4 hold greyed cards that
    # have never been lit in the hand (fireball was only ever seen as the Next thumbnail).
    names, ready, upcoming = reads["008_16s.jpg"]
    assert names[0] == "arrows" and names[1] == "knight"
    assert names[3] == "fireball" and ready == [True, True, False, False]
    assert names[2] in ("mini_pekka", "unknown")  # never shown to the reader before, so unknown is accepted
    assert upcoming == "musketeer"


@pytest.mark.parametrize("path", [LIT, GREY])
def test_fixtures_exist(path):
    assert path.exists()


def test_a_card_washed_out_by_the_wipe_over_unaffordable_cards_is_still_read():
    """A real hand at 0 elixir: the game draws every card almost white, with a lighter wedge that sweeps round as
    the elixir arrives."""
    hand = HandReader().read(_reference_from_strip(FIXTURES / "hand_washed_out.jpg"))
    assert [card.name for card in hand] == ["knight", "giant", "musketeer", "mini_pekka"]
    assert not any(card.ready for card in hand)
