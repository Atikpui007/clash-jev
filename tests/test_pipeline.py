"""screenshot -> state -> valid moves -> decision -> clicks, on a real battle frame (no emulator, no network).

tests/fixtures/battle_419x633.png is a frame from a live match on a tablet, drawn on the reference layout:
4 elixir; minions, arrows, mini pekka and knight in hand, musketeer next; my giant at the enemy's left
tower, which has fallen. No enemy troop is out in it, so `_with_enemies` puts two on the board: a
balloon on my left side and an unnamed troop on their right.
"""

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import cv2
import pytest

from clash_jev import pipeline
from clash_jev.moves import get_valid_moves, legal_squares
from clash_jev.perception import Perception
from clash_jev.policy import (
    BaselinePolicy,
    JevPolicy,
    build_card_question,
    build_square_question,
    build_state,
    build_strategy_question,
)
from clash_jev.state import BattleState, HandCard, Towers
from clash_jev.strategies import HOLD, SAVE, STRATEGIES
from clash_jev.units import Unit

FRAME = Path(__file__).parent / "fixtures" / "battle_419x633.png"


@pytest.fixture
def frame():
    return cv2.imread(str(FRAME))


class _Enemies:
    """Stands in for the troop network: adds an enemy balloon on my left side and an unnamed enemy troop."""

    def name_units(self, _frame, units):
        return (*units, Unit("enemy", 0.229, 0.46, 0.56, "balloon"), Unit("enemy", 0.70, 0.30, None, None))


def _with_enemies() -> Perception:
    perception = Perception()
    perception.identifier = _Enemies()
    return perception


def _without_detector() -> Perception:
    perception = Perception()
    perception.identifier = None
    return perception


def test_extract_state_reads_the_real_frame(frame):
    state = _without_detector().extract_state(frame, elapsed_s=17)
    assert state.elixir == 4 and state.next_card == "musketeer"
    assert [card.name for card in state.hand] == ["minions", "arrows", "mini_pekka", "knight"]
    assert all(card.ready for card in state.hand)
    assert state.left.mine_on_their_side == 1  # my giant, at their left tower
    assert sum(vars(state.left).values()) + sum(vars(state.right).values()) == 1  # and nothing else
    assert state.units[0].owner == "mine" and state.units[0].health < 0.3
    towers = state.towers
    assert towers.enemy_left is None and (towers.enemy_right, towers.my_left, towers.my_right) == (
        1.0,
        1.0,
        1.0,
    )  # full bars read as full

    state = _with_enemies().extract_state(frame, elapsed_s=17)
    assert (state.left.enemy_on_my_side, state.right.enemy_on_their_side) == (1, 1)


@pytest.mark.parametrize("width", [1440, 1080, 720, 540])
def test_any_resolution_reads_the_same(width):
    """The tablet's own screen shape (not the reference shape), at the sizes a device or its video stream sends."""
    tablet = cv2.imread(str(FRAME.with_name("tablet_hand_grey.png")))
    frame = cv2.resize(tablet, (width, round(width * 1.6)), interpolation=cv2.INTER_LINEAR)
    state = _without_detector().extract_state(frame)
    assert (state.elixir, state.next_card) == (0, "musketeer")
    assert [card.name for card in state.hand] == ["minions", "arrows", "mini_pekka", "knight"]
    # Three enemy troops stand side by side at their left tower; their badges are 10 px tall on the reference
    # layout, and only survive being read from the larger drawing.
    assert [unit.owner for unit in state.units].count("enemy") == 3


def test_damaged_then_destroyed_tower(frame, monkeypatch):
    from clash_jev import perception as module

    clock = {"now": 1000.0}
    monkeypatch.setattr(module.time, "time", lambda: clock["now"])
    perception = _without_detector()
    perception.extract_state(frame)
    frame[88:104, 305:335] = (60, 170, 120)  # grass over the right 60% of the enemy-right bar
    damaged = perception.extract_state(frame).towers.enemy_right
    assert 0.3 <= damaged <= 0.5
    frame[88:104, 269:335] = (60, 170, 120)  # bar gone entirely
    # A hidden bar is not a verdict: for the first seconds the tower keeps its last reading.
    assert perception.extract_state(frame).towers.enemy_right == damaged
    clock["now"] += 2
    assert perception.extract_state(frame).towers.enemy_right == damaged
    clock["now"] += 3  # gone for five seconds without a break
    towers = perception.extract_state(frame).towers
    assert towers.enemy_right == 0.0 and towers.my_left == 1.0
    assert towers.enemy_left is None or towers.enemy_left == 0.0  # never seen standing: no reading to keep


def test_a_screen_with_no_hand_offers_nothing_to_ask_about(frame):
    """There is no battle detection: a menu simply yields no identified card, so no valid move."""
    frame[:] = 40
    assert get_valid_moves(Perception().extract_state(frame)) == []


def _state(elixir: int, names=("giant", "fireball", "cannon", "knight"), **overrides) -> BattleState:
    hand = tuple(HandCard(slot, name, True) for slot, name in enumerate(names))
    return BattleState(elapsed_s=130, elixir=elixir, hand=hand, **overrides)


def test_valid_moves_respect_cost_readiness_and_card_kind():
    moves = {move.card.name: [square.name for square in move.squares] for move in get_valid_moves(_state(4))}
    assert set(moves) == {"fireball", "cannon", "knight"}  # giant costs 5
    assert moves["fireball"] == ["left_enemy_tower", "right_enemy_tower", "enemy_king_tower"]  # no troops out
    assert "left_bridge" in moves["knight"] and "left_enemy_tower" not in moves["knight"]
    assert moves["cannon"] == ["left_tower_front", "right_tower_front", "centre_king_front"]

    greyed = BattleState(elapsed_s=0, elixir=10, hand=(HandCard(0, "knight", False),))
    assert get_valid_moves(greyed) == []


def test_evolutions_and_heroes_use_their_base_card():
    move = get_valid_moves(_state(3, names=("evo_knight", "hero_giant", "unknown", "unknown")))
    assert [option.card.name for option in move] == [
        "evo_knight"
    ]  # hero_giant costs 5; unknown is never offered


def test_a_spell_is_only_ever_cast_on_an_enemy_tower_or_an_enemy_troop(frame):
    from clash_jev.state import HandCard as Card

    state = _with_enemies().extract_state(frame, elapsed_s=30)
    state = replace(state, towers=replace(state.towers, enemy_left=0.4))
    arrows = legal_squares(Card(0, "arrows", True), state)
    names = [square.name for square in arrows]
    assert names[:3] == ["left_enemy_tower", "right_enemy_tower", "enemy_king_tower"]
    troop_targets = [
        square for square in arrows if square.name.startswith("enemy_") and "tower" not in square.name
    ]
    assert len(troop_targets) == 2 and any(
        "balloon" in square.meaning and "left lane" in square.meaning for square in troop_targets
    )
    balloon = next(square for square in troop_targets if "balloon" in square.name)
    assert (
        abs(balloon.xy[0] - 0.229) < 0.01 and 0.45 < balloon.xy[1] < 0.50
    )  # aimed where the balloon is standing
    # No square of my own half, and no empty ground: nothing to waste a spell on.
    assert not any(
        name in names for name in ("left_bridge", "left_tower_front", "centre_king_front", "left_pocket")
    )

    quiet = replace(state, units=())
    assert [square.name for square in legal_squares(Card(0, "arrows", True), quiet)] == names[
        :3
    ]  # towers only
    fallen = replace(quiet, towers=replace(quiet.towers, enemy_left=0.0))
    assert [sq.name for sq in legal_squares(Card(0, "arrows", True), fallen)] == [
        "right_enemy_tower",
        "enemy_king_tower",
    ]
    # Royal delivery cannot be cast on the enemy half: with no enemy troop on my side it has no target at all.
    assert [sq.name for sq in legal_squares(Card(0, "royal_delivery", True), state)] == [balloon.name]
    assert legal_squares(Card(0, "royal_delivery", True), quiet) == ()


def test_pocket_opens_when_an_enemy_tower_is_down():
    knight = get_valid_moves(_state(10, towers=Towers(enemy_left=0.0, enemy_right=0.4)))[-1]
    names = [square.name for square in knight.squares]
    assert "left_pocket" in names and "right_pocket" not in names


def test_jev_is_offered_everything_at_every_step(frame):
    state = _with_enemies().extract_state(frame, elapsed_s=130)
    # Step 1: the fixed list, whatever the board or the hand look like. Doing nothing is always on it.
    offered = set(build_strategy_question(list(STRATEGIES))["strategy"].criteria)
    assert {SAVE, "defend_left", "defend_right", "push_left", "push_right", "build_push"} <= offered
    assert (
        "wait" not in offered and HOLD in offered
    )  # two ways of not playing: save for your own play, hold for theirs
    hold = build_strategy_question(list(STRATEGIES))["strategy"].criteria[HOLD]
    assert "in reserve" in hold["what"] and "answers best" in hold["what"] and "caps at 10" in hold["not_for"]
    assert (
        "your side" not in hold["not_for"]
    )  # holding is also waiting for the right answer to a threat that is here
    assert {"counter_push_left", "split_push", "cycle"} <= offered and "chip_damage" not in offered
    # A strategy is a concept: its text names no card type and no square.
    texts = " ".join(strategy.meaning for strategy in STRATEGIES).lower()
    assert not any(
        word in texts for word in ("spell", "troop", "tank", "building", "bridge", "deploy", "card at")
    )
    # Step 2: every card in the hand, not a subset picked to suit the strategy.
    cards = build_card_question(state.hand)["card"].criteria
    assert set(cards) == {
        "play_minions_slot0",
        "play_arrows_slot1",
        "play_mini_pekka_slot2",
        "play_knight_slot3",
    }
    # Step 3: every square the game allows that card on. Placement rules only.
    mini_pekka = state.hand[2]
    squares = build_square_question(legal_squares(mini_pekka, state))["square"].criteria
    assert set(squares) == {
        "left_bridge",
        "right_bridge",
        "left_tower_front",
        "right_tower_front",
        "left_back",
        "right_back",
        "centre",
        "centre_king_front",
    }
    sent = build_state(state)
    # Jev is told what it is playing: the game, the objective, the rules and the vocabulary.
    assert sent["game"]["name"] == "Clash Royale"
    assert "asked again at the next snapshot" in sent["game"]["how_you_play"]
    assert sent["clock"]["seconds_between_snapshots"] == 1.0
    assert sent["clock"]["seconds_per_elixir"] == 1.4  # 130 s in: double elixir
    assert [card["elixir_left_after_playing"] for card in sent["hand"]] == [
        1,
        1,
        0,
        1,
    ]  # 4 elixir; costs 3, 3, 4, 3
    assert sent["game"]["objective"].startswith("Your goal is to destroy the enemy's towers")
    for question in (build_strategy_question(list(STRATEGIES)), build_card_question(state.hand)):
        (asked,) = question.values()
        assert (
            "destroy the enemy's towers, above all their king tower, before they destroy yours"
            in asked.instructions
        )
    assert {"bridge", "lane", "pocket", "win condition", "tank", "swarm", "elixir leak"} <= set(
        sent["game"]["glossary"]
    )
    assert "limits what you can carry out" in sent["game"]["elixir_and_strategy"]
    assert "next_card" in {st.name: st.meaning for st in STRATEGIES}["cycle"]
    save = build_strategy_question(list(STRATEGIES))["strategy"].criteria[SAVE]
    assert save["what"].startswith("Play nothing now. Let your elixir build up")
    criteria = build_strategy_question(list(STRATEGIES))["strategy"].criteria
    assert all(
        isinstance(option, dict) and option["not_for"] for option in criteria.values()
    )  # every one has a boundary
    assert "close to your tower" in criteria["defend_left"]["not_for"]
    assert "defend_centre" in criteria
    assert criteria["counter_push_right"]["not_for"].endswith("push_right.")
    assert (
        "caps at 10" in save["not_for"]
        and "wasted" in save["not_for"]
        and "Do not leak elixir" in save["not_for"]
        and "worst choice" in save["not_for"]
    )
    # Leaking is stated as a fact of the game, with no instruction to avoid it.
    assert (
        "aim to play" not in sent["game"]["elixir"]
        and "Avoided" not in sent["game"]["glossary"]["elixir leak"]
    )
    assert "leaking elixir" in sent["game"]["elixir"] and sent["elixir_leak"] == {
        "leaking_now": False,
        "seconds_at_10": 0.0,
    }
    assert sent["lanes"]["left"]["enemy_on_my_side"] == 1
    assert sent["clock"]["elixir_rate"] == "double"
    assert [(c["card"], c["elixir_cost"], c["class"], c["health"], c["targets"]) for c in sent["hand"]] == [
        ("minions", 3, "swarm", "very low", "air and ground"),
        ("arrows", 3, "spell", None, "air and ground"),
        ("mini_pekka", 4, "melee fighter", "medium", "ground only"),
        ("knight", 3, "mini tank", "high", "ground only"),
    ]
    # Every card says what type it is, and the three types are defined once in the briefing.
    assert [card["type"] for card in sent["hand"]] == ["troop", "spell", "troop", "troop"]
    assert set(sent["game"]["card_types"]) == {"troop", "building", "spell"}
    # A card is described the way the game describes it, with no notes on how or when to use it.
    knight = sent["hand"][3]
    assert knight["description"].startswith("One ground melee troop. Sturdy: high health")
    assert "Cannot attack flying troops" in knight["weaknesses"] and knight["strengths"]
    assert not any(
        "great on" in card["description"] or "play " in card["description"].lower() for card in sent["hand"]
    )
    # The state gives each card's elixir cost and the current elixir, with no affordability fields.
    assert not any(
        key in card
        for card in sent["hand"]
        for key in ("playable_now", "elixir_needed", "seconds_until_affordable")
    )
    # An enemy troop is described by what it is, with no list of the cards that answer it.
    assert not any("cards_that_can_attack_it" in troop for troop in sent["enemy_troops"])
    # My own troops on the board are listed too, the same way. What the bot itself played is not part of it.
    labelled = build_state(replace(state, units=(Unit("mine", 0.3, 0.3, None, played_as="knight"),)))
    assert labelled["my_troops"][0]["troop"] == "unidentified" and "knight" not in str(labelled["my_troops"])
    mine = build_state(replace(state, units=(Unit("mine", 0.3, 0.3, 0.5, "giant"),)))["my_troops"]
    assert [(t["troop"], t["lane"], t["where"], t["health_remaining"]) for t in mine] == [
        ("giant", "left", "their side", 0.5)
    ] and "tank" in mine[0]["archetypes"]
    # An identified enemy troop carries exactly the profile the same card would carry in your hand.
    from clash_jev.cards import profile

    minions = build_state(replace(state, units=(Unit("enemy", 0.3, 0.3, None, "minions"),)))["enemy_troops"][
        0
    ]
    assert {key: minions[key] for key in profile("minions")} == profile("minions")
    assert minions["flies"] and "swarm" in minions["archetypes"] and minions["weaknesses"]

    # How far a troop is from the tower it is heading for, in tiles; the king tower once that princess tower fell.
    def distance(unit, **towers):
        told = build_state(replace(state, units=(unit,), towers=replace(state.towers, **towers)))
        (troop,) = told["enemy_troops"] or told["my_troops"]
        return {key: troop[key] for key in troop if key.startswith("tiles_") or key == "that_tower"}

    at_their_tower = Unit("enemy", 0.28, 0.19, None, "giant")  # just played, standing at their own left tower
    assert distance(at_their_tower, my_left=1.0) == {
        "tiles_from_my_tower": 17,
        "that_tower": "left princess tower",
    }
    on_my_tower = Unit("enemy", 0.29, 0.56, None, "giant")
    assert distance(on_my_tower, my_left=1.0)["tiles_from_my_tower"] <= 1
    assert distance(on_my_tower, my_left=0.0)["that_tower"] == "king tower"
    assert distance(Unit("mine", 0.72, 0.30, None), enemy_right=0.5) == {
        "tiles_from_enemy_tower": 5,
        "that_tower": "right princess tower",
    }
    balloon = next(troop for troop in sent["enemy_troops"] if troop["troop"] == "balloon")
    assert balloon["flies"] and balloon["class"] == "win condition" and balloon["health"] == "high"
    assert balloon["lane"] == "left" and balloon["where"] == "my side" and balloon["health_remaining"] == 0.56


def _jev(system_one) -> JevPolicy:
    policy = JevPolicy.__new__(JevPolicy)
    policy.client = SimpleNamespace(system_one=system_one)
    policy.fallback = BaselinePolicy()
    return policy


def _answer(choice: str) -> SimpleNamespace:
    return SimpleNamespace(choice=choice, probabilities={choice: 1.0}, confidence=1.0)


def test_jev_is_always_asked_all_three_and_code_only_refuses_the_impossible(frame):
    state = _without_detector().extract_state(frame, elapsed_s=130)
    options = get_valid_moves(state)
    answers = {
        "strategy": _answer("push_left"),
        "card": _answer("play_minions_slot0"),
        "square": _answer("right_back"),
    }
    sent = []

    def system_one(sent_state, questions):
        sent.append((sent_state, questions))
        return SimpleNamespace(choices=answers)

    played = _jev(system_one).decide(state, options)
    # The picks are executed as given, even a square that does not match the strategy.
    assert (played.card.name, played.square.name, played.source) == ("minions", "right_back", "jev")
    assert [list(questions) for _, questions in sent] == [["strategy"], ["card"], ["square"]]
    assert len(sent[1][1]["card"].criteria) == 4 and len(sent[2][1]["square"].criteria) == 8
    assert sent[1][0]["strategy"]["name"] == "push_left" and sent[2][0]["playing"]["card"] == "minions"
    assert played.detail["requests_made"] == 3

    # A picked card that cannot be played right now is declined.
    poor = replace(state, elixir=3)
    sent.clear()
    answers["card"] = _answer("play_mini_pekka_slot2")  # costs 4
    declined = _jev(system_one).decide(poor, get_valid_moves(poor))
    assert declined.card is None and "cannot be played right now" in declined.detail["note"]
    assert [list(questions) for _, questions in sent] == [["strategy"], ["card"]]

    sent.clear()
    answers["strategy"] = _answer(SAVE)
    saved = _jev(system_one).decide(state, options)
    assert saved.card is None and len(sent) == 1  # doing nothing asks for no card and no square

    def broken(*_):
        raise TimeoutError

    failed = _jev(broken).decide(_state(6), get_valid_moves(_state(6)))
    assert failed.source == "fallback" and failed.card is not None


def test_step_clicks_the_chosen_card_then_the_chosen_square(frame, monkeypatch):
    taps = []
    device = SimpleNamespace(frame=lambda: frame, tap=lambda x, y: taps.append((x, y)))
    answers = {
        "strategy": _answer("defend_left"),
        "card": _answer("play_mini_pekka_slot2"),
        "square": _answer("left_tower_front"),
    }
    monkeypatch.setattr(pipeline, "_jev", _jev(lambda *_: SimpleNamespace(choices=answers)))

    move = pipeline.step(device)
    assert (move.card.name, move.square.name) == ("mini_pekka", "left_tower_front")
    assert taps == [(int(0.649 * 419), int(0.886 * 633)), (int(0.36 * 419), int(0.545 * 633))]


def test_opponent_elixir_refills_and_pays_for_new_troops():
    from clash_jev.opponent import OpponentElixir
    from clash_jev.units import Unit

    opponent = OpponentElixir()
    assert opponent.update(0, "single", ()) == 5.0
    assert opponent.update(2.8, "single", ()) == 6.0
    balloon = Unit("enemy", 0.25, 0.30, None, "balloon")
    assert opponent.update(2.8, "single", (balloon,)) == 1.0  # balloon costs 5
    moved = Unit("enemy", 0.25, 0.36, 0.9, "balloon")
    assert opponent.update(5.6, "single", (moved,)) == 2.0  # same troop walking: not charged again
    swarm = tuple(Unit("enemy", 0.70 + i * 0.03, 0.30, None) for i in range(3))
    assert opponent.update(5.6, "single", (moved, *swarm)) == 0.0  # one unidentified card, not three
    assert opponent.update(300, "triple", (moved, *swarm)) == 10.0


def test_time_spent_at_full_elixir_is_tracked_and_resets(frame):
    layout = Perception().layout
    full = frame.copy()
    for x in layout.elixir_x:  # light all ten pips
        full[int(layout.elixir_y * 633), int(x * 419)] = layout.elixir_bgr
    perception = Perception()
    assert perception.extract_state(frame, 10).seconds_at_full_elixir == 0.0  # 5 elixir
    assert perception.extract_state(full, 12).seconds_at_full_elixir == 0.0  # just reached 10
    leaking = perception.extract_state(full, 15.5)
    assert leaking.elixir == 10 and leaking.seconds_at_full_elixir == 3.5
    assert build_state(leaking)["elixir_leak"] == {"leaking_now": True, "seconds_at_10": 3.5}
    assert perception.extract_state(frame, 17).seconds_at_full_elixir == 0.0  # spent some: the leak stops


def test_enemy_troop_pictures_are_collected_only_when_asked_and_only_in_battle(frame, tmp_path, monkeypatch):
    _with_enemies().extract_state(frame)
    monkeypatch.setenv("CLASH_JEV_COLLECT", str(tmp_path))
    _with_enemies().extract_state(frame)
    saved = sorted(str(path.parent.relative_to(tmp_path)) for path in tmp_path.rglob("*.jpg"))
    assert saved == [
        "enemy/balloon",
        "enemy/unnamed",
        "frames",
        "mine/unnamed",
    ]  # my giant too
    frame[500:] = 40  # no hand on screen: not a battle, nothing is saved
    _with_enemies().extract_state(frame)
    assert len(list(tmp_path.rglob("*.jpg"))) == 4


def test_a_pick_that_could_not_be_played_is_a_fact_in_the_next_state(battle_state=None):
    from clash_jev.policy import JevPolicy, build_state
    from clash_jev.state import BattleState, HandCard

    hand = tuple(
        HandCard(slot, name, True) for slot, name in enumerate(("fireball", "knight", "archers", "giant"))
    )
    policy = JevPolicy.__new__(JevPolicy)
    policy._unplayed = ("fireball", 10.0)
    fact = policy._unplayed_pick(BattleState(elapsed_s=11.0, elixir=2, hand=hand))
    assert fact == {
        "card": "fireball",
        "elixir_cost": 4,
        "more_elixir_needed_now": 2,
        "picked_seconds_ago": 1.0,
    }
    assert build_state(BattleState(elapsed_s=11.0, elixir=2, hand=hand), fact)["your_unplayed_pick"] == fact
    # Another match (the clock went back) or a card that left the hand: nothing is reported.
    assert policy._unplayed_pick(BattleState(elapsed_s=3.0, elixir=2, hand=hand)) is None
    assert policy._unplayed_pick(BattleState(elapsed_s=11.0, elixir=2, hand=hand[1:])) is None
