"""Every id any reader can produce must have complete, valid facts."""

import json

import cv2
import pytest

from clash_jev import hand
from clash_jev.cards import CARDS, TAGS, base_name, hits_air, info, known, profile, tags


def test_every_card_the_hand_reader_knows_has_facts():
    shapes = json.loads(hand.CARD_SHAPES.read_text())
    assert sorted(name for name in shapes if not known(name)) == []
    assert all(len(card["shape"]) == 14 * 16 and len(card["detail"]) == 28 * 32 for card in shapes.values())


def test_facts_are_complete_and_consistent():
    for name, card in CARDS.items():
        assert card.role and card.tags <= TAGS, name
        assert card.cost is None or 1 <= card.cost <= 9, name
        if card.kind == "spell":
            assert "flying" not in card.tags, name
        if card.kind in ("troop", "anywhere_troop") and name not in ("spirit_empress",):
            assert card.cost is not None, name
    assert {name for name, card in CARDS.items() if card.cost is None} == {"mirror", "spirit_empress"}


def test_variants_inherit_and_are_labelled():
    assert info("evo_knight") == info("knight") and "evolution" in tags("evo_knight")
    assert "hero" in tags("hero_bowler") and base_name("hero_bowler") == "bowler"


def test_what_a_card_can_hit_is_a_fact_of_the_card():
    assert hits_air("ice_wizard") and not hits_air("bowler") and hits_air("unknown") is None
    assert profile("knight")["targets"] == "ground only" and profile("giant")["targets"] == "buildings only"
    assert profile("log")["targets"] == "ground only" and profile("fireball")["targets"] == "air and ground"


def test_add_card_teaches_a_card_the_reader_does_not_know(tmp_path, monkeypatch):
    frame = cv2.imread("tests/fixtures/battle_419x633.png")
    shapes = json.loads(hand.CARD_SHAPES.read_text())
    del shapes["minions"]
    (tmp_path / "shapes.json").write_text(json.dumps(shapes))
    monkeypatch.setattr(hand, "CARD_SHAPES", tmp_path / "shapes.json")
    monkeypatch.setattr(hand, "EXTRA_CARD_SHAPES", tmp_path / "extra.json")

    assert hand.read_hand(frame)[0].name == "unknown"
    hand.add_card(frame, 0, "evo_minions")
    assert hand.read_hand(frame)[0].name == "evo_minions"
    assert "evo_minions" in json.loads((tmp_path / "extra.json").read_text())


@pytest.mark.parametrize("name", ["evo_valkyrie", "hero_giant", "evo_pekka", "spirit_empress", "mirror"])
def test_variants_and_contextual_cards_have_facts(name):
    assert known(name) and info(name).role


def test_every_card_has_archetypes_and_every_archetype_is_defined_in_the_briefing():
    from clash_jev.cards import archetypes
    from clash_jev.game import GAME

    defined = set(GAME["archetypes"])
    for name in CARDS:
        labels = archetypes(name)
        assert labels, name
        assert set(labels) <= defined, (name, set(labels) - defined)
    assert archetypes("mini_pekka") == ["tank buster", "high damage"]
    assert {"mini tank", "splash"} <= set(archetypes("valkyrie"))
    assert archetypes("giant") == ["win condition", "tank", "building targeter"]
    assert archetypes("fireball") == ["medium spell"] and archetypes("evo_knight") == archetypes("knight")
    assert "tank" in GAME["archetypes"]["tank buster"].lower()  # the definition states the matchup


def test_an_arena_limits_which_cards_an_opponent_can_own():
    from clash_jev.cards import unlock_arena, unlocked_by

    assert unlock_arena("knight") == 0 and unlock_arena("evo_knight") == 0
    assert unlocked_by(1) == {
        "knight", "archers", "giant", "minions", "musketeer", "mini_pekka", "fireball", "arrows",
        "goblins", "spear_goblins", "goblin_hut", "goblin_cage",
    }  # fmt: skip
    assert "balloon" not in unlocked_by(6) and "balloon" in unlocked_by(7)


def test_every_card_of_the_first_arenas_is_described_without_telling_jev_how_to_play_it():
    from clash_jev.cards import describe, unlocked_by

    for name in unlocked_by(2):  # the training camp and arenas 1 and 2
        told = describe(name)
        assert told["description"] and told["strengths"] and told["weaknesses"], name
        text = " ".join([told["description"], *told["strengths"], *told["weaknesses"]]).lower()
        # No wording about when, where or whether to play the card, and nothing about its price, which
        # `elixir_cost` already states.
        assert not any(
            word in text
            for word in (
                "play it",
                "place",
                "use it",
                "should",
                "best ",
                "good for",
                "defend",
                "push",
                "cheap",
                "expensive",
                "cost",
            )
        ), name
    assert describe("pekka") == {} and describe("evo_knight") == describe("knight")
