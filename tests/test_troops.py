"""The project's own troop network: it names troops on real frames, for both sides, through OpenCV alone."""

import json
from pathlib import Path

import cv2
import numpy
import pytest

from clash_jev.cards import known
from clash_jev.perception import Perception
from clash_jev.troops import MODEL_FACTS, SIZE, TroopClassifier, network_input, troop_picture

FIXTURES = Path(__file__).parent / "fixtures"
pytestmark = pytest.mark.skipif(
    not TroopClassifier.available(), reason="no trained troop network in this checkout"
)


def test_it_names_my_giant_on_a_real_frame_and_the_bot_uses_it():
    perception = Perception()
    assert isinstance(perception.identifier, TroopClassifier)
    state = perception.extract_state(cv2.imread(str(FIXTURES / "tablet_hand_lit.png")))
    assert [(unit.owner, unit.name) for unit in state.units] == [("mine", "giant")]


def test_every_card_it_knows_has_facts_and_an_arena_limits_its_answers():
    facts = json.loads(MODEL_FACTS.read_text())
    assert facts["cards"] and all(known(card) for card in facts["cards"])
    training_camp = TroopClassifier(arena=0)
    picture = numpy.random.default_rng(0).integers(0, 255, (152, 150, 3), dtype=numpy.uint8)
    card, confidence = training_camp.name([picture])[0]
    assert (
        card in {"knight", "archers", "giant", "minions", "musketeer", "mini_pekka"} and 0 < confidence <= 1
    )
    assert TroopClassifier().name([]) == []


def test_a_troop_picture_is_cut_under_its_badge_and_read_at_a_fixed_size():
    frame = numpy.zeros((1266, 838, 3), numpy.uint8)
    picture = troop_picture(frame, 0.5, 0.5)
    assert all(149 <= side <= 153 for side in picture.shape[:2])  # 0.18 of the width by 0.12 of the height
    assert troop_picture(frame, 0.01, 0.0).size > 0  # at the edge of the arena the picture is simply smaller
    assert network_input(picture).shape == (3, SIZE, SIZE)
