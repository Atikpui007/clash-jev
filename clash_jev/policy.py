"""Policies: BattleState + legal moves -> one Decision.

JevPolicy decides in three steps, each depending on the one before, so each is its own request:
  1. `strategy`: one of the full, fixed list of strategies (strategies.py), including doing nothing.
  2. `card`: one of every card in the hand.
  3. `square`: one of every square the game allows that card on.
Every step is asked with its full option list. A chosen card that cannot be played right now is not tapped.
"""

import time
from dataclasses import asdict, dataclass, field
from typing import Any, Protocol

from clash_jev.cards import info, profile
from clash_jev.game import GAME
from clash_jev.moves import CardMoves, Square, legal_squares
from clash_jev.state import BattleState, HandCard
from clash_jev.strategies import NO_PLAY, STRATEGIES, Strategy

# Describes every field of the state that is sent.
_STATE_GUIDE = (
    "`game` explains what this game is, its objective, how the arena, elixir and cards work, and the "
    "terms used here. The rest is the match at this instant. `clock` is the time since play was started, how many seconds pass between the snapshots you are shown, and how many seconds one elixir takes to arrive. `elixir_leak` says whether you are at the 10 cap right now, leaking elixir, and for how long. `elixir` is what you can spend (max 10) and `elixir_rate` is how fast it refills. `hand` lists "
    "every card you hold: its `type` (troop, building or spell: each defined in `game.card_types`), its `elixir_cost`, the `elixir_left_after_playing` it (your elixir minus its cost), its `archetypes` (each defined in `game.archetypes`, with what that "
    "kind of card is strong and weak against), its `class` (tank, mini tank, ranged support, swarm, win condition, spell, "
    "building), `health` and `damage` levels, what it `targets` (ground only, air and ground, or buildings "
    "only), whether it `flies`, its `abilities`, for a spell the `area` it covers, and a plain `description` "
    "of what the card is with its `strengths` and `weaknesses`: what it is strong and weak against. "
    "`next_card` replaces whatever you play. `your_unplayed_pick` is the card you picked at the previous snapshot "
    "when it could not be played then, with its cost, how much more elixir it needs now and how many seconds ago "
    "you picked it; it is null when your previous pick was played or you picked no card. `lanes` counts the troops seen in each lane: `enemy_*` "
    "are the opponent's, `mine_*` are yours, split by your side, the bridge, and their side. "
    "`my_troops` lists your own troops that are on the board. "
    "`enemy_troops` lists the opponent's troops. Both carry the same card profile when the troop could be "
    "identified, where they are, how far each is from the tower it is walking toward (`tiles_from_my_tower` for the opponent's troops, `tiles_from_enemy_tower` for yours, with `that_tower` naming it; the arena is 18 tiles wide and 32 long, and the two princess towers of a lane stand about 17 tiles apart), how long each has been in view (`seen_for_seconds`) and their `health_remaining` (0-1). `towers` is each tower's health from 0 "
    "(destroyed) to 1 (full). `enemy_elixir_estimate` is a tracked estimate of the opponent's "
    "elixir."
)

_GOAL = "Your goal is to destroy the enemy's towers, above all their king tower, before they destroy yours. "

STRATEGY_INSTRUCTIONS = (
    "You are playing a live Clash Royale match. "
    + _GOAL
    + _STATE_GUIDE
    + " The options are the full list of strategies, including playing nothing. What a strategy costs "
    "is paid from `elixir`, the amount you hold right now. Choose the strategy to follow right now."
)

CARD_INSTRUCTIONS = (
    "You are playing a live Clash Royale match and have chosen the strategy in `strategy`. "
    + _GOAL
    + _STATE_GUIDE
    + " Choose the card to play for that strategy."
)

SQUARE_INSTRUCTIONS = (
    "You are playing a live Clash Royale match, following the strategy in `strategy`, and have "
    "decided to play `playing.card` right now; `playing` describes it. "
    + _GOAL
    + _STATE_GUIDE
    + " Choose the "
    "square to deploy it on."
)


@dataclass
class Decision:
    card: HandCard | None  # None = nothing is played
    square: Square | None
    source: str
    detail: dict[str, Any] = field(default_factory=dict)


class Policy(Protocol):
    def decide(self, state: BattleState, moves: list[CardMoves]) -> Decision: ...


def _option(card: HandCard) -> str:
    return f"play_{card.name}_slot{card.slot}"


_SECONDS_PER_ELIXIR = {"single": 2.8, "double": 1.4, "triple": 0.93}


def _waiting_cost(name: str, state: BattleState) -> dict[str, Any]:
    """How far a card you cannot afford is from being playable, in elixir and in seconds."""
    cost = info(name).cost
    if cost is None or cost <= state.elixir:
        return {}
    needed = cost - state.elixir
    return {
        "elixir_needed": needed,
        "seconds_until_affordable": round(needed * _SECONDS_PER_ELIXIR[state.elixir_rate], 1),
    }


# Where the towers stand on the reference layout, and the size of one arena tile there (the arena is 18
# tiles wide and 32 long). A troop stands a little below its level badge.
_TOWERS = {
    ("mine", "left"): (0.28, 0.60),
    ("mine", "right"): (0.72, 0.60),
    ("mine", "king"): (0.50, 0.70),
    ("enemy", "left"): (0.28, 0.22),
    ("enemy", "right"): (0.72, 0.22),
    ("enemy", "king"): (0.50, 0.125),
}
_TILE = (0.74 / 18, 0.70 / 32)
_TROOP_BELOW_BADGE = 0.03


def _tiles_to_tower(unit, state: BattleState) -> dict[str, Any]:
    """How far a troop is from the tower it walks toward, in tiles: the other side's princess tower in its
    lane, or their king tower once that princess tower has fallen."""
    lane = "left" if unit.x < 0.5 else "right"
    target_side = "mine" if unit.owner == "enemy" else "enemy"
    health = getattr(state.towers, f"{'my' if target_side == 'mine' else 'enemy'}_{lane}")
    tower = "king" if health == 0 else lane
    x, y = _TOWERS[(target_side, tower)]
    across, along = (unit.x - x) / _TILE[0], (unit.y + _TROOP_BELOW_BADGE - y) / _TILE[1]
    key = "tiles_from_my_tower" if unit.owner == "enemy" else "tiles_from_enemy_tower"
    return {
        key: round((across**2 + along**2) ** 0.5),
        "that_tower": f"{tower} tower" if tower == "king" else f"{lane} princess tower",
    }


def _troop(unit, state: BattleState) -> dict[str, Any]:
    """A troop on the board, yours or the opponent's: the card's profile plus where it is and its health."""
    return {
        "troop": unit.name or "unidentified",
        **(profile(unit.name) if unit.name else {"class": "unknown", "archetypes": []}),
        "lane": "left" if unit.x < 0.5 else "right",
        "where": "their side" if unit.y < 0.37 else "bridge" if unit.y < 0.445 else "my side",
        **_tiles_to_tower(unit, state),
        "seen_for_seconds": unit.seen_for_s,
        "health_remaining": unit.health if unit.health is not None else 1.0,
    }


def build_state(state: BattleState, unplayed_pick: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "game": GAME,
        "clock": {
            "elapsed_seconds": round(state.elapsed_s),
            "elixir_rate": state.elixir_rate,
            "seconds_between_snapshots": state.snapshot_interval_s,
            "seconds_per_elixir": state.seconds_per_elixir,
        },
        "elixir": state.elixir,
        "elixir_leak": {
            "leaking_now": state.elixir >= 10,
            "seconds_at_10": state.seconds_at_full_elixir,
        },
        "hand": [
            {
                "card": card.name,
                "elixir_cost": info(card.name).cost,
                "elixir_left_after_playing": None
                if info(card.name).cost is None
                else state.elixir - info(card.name).cost,
                **profile(card.name),
            }
            for card in state.hand
        ],
        "next_card": state.next_card or "unknown",
        "your_unplayed_pick": unplayed_pick,
        "enemy_elixir_estimate": state.enemy_elixir_estimate,
        "lanes": {"left": asdict(state.left), "right": asdict(state.right)},
        "my_troops": [_troop(unit, state) for unit in state.units if unit.owner == "mine"],
        "enemy_troops": [_troop(unit, state) for unit in state.units if unit.owner == "enemy"],
        "towers": {
            name: "not observed" if value is None else value for name, value in asdict(state.towers).items()
        },
    }


def _card_facts(name: str) -> dict[str, Any]:
    return {"card": name, "elixir_cost": info(name).cost, **profile(name)}


def build_strategy_question(strategies: list[Strategy]) -> dict[str, Any]:
    from typesafe_sdk import Choice

    # An option that has a case it does not cover says so in its own `not_for` field (structured criteria).
    criteria = {
        strategy.name: {"what": strategy.meaning, "not_for": strategy.not_for}
        if strategy.not_for
        else strategy.meaning
        for strategy in strategies
    }
    return {"strategy": Choice(instructions=STRATEGY_INSTRUCTIONS, criteria=criteria)}


def build_card_question(hand: tuple[HandCard, ...]) -> dict[str, Any]:
    from typesafe_sdk import Choice

    criteria = {
        _option(card): "Play the card in this slot; it could not be identified."
        if card.name == "unknown"
        else f"Play {card.name.replace('_', ' ')} ({profile(card.name)['class']}, elixir cost {info(card.name).cost})."
        for card in hand
    }
    return {"card": Choice(instructions=CARD_INSTRUCTIONS, criteria=criteria)}


def build_square_question(squares: tuple[Square, ...]) -> dict[str, Any]:
    from typesafe_sdk import Choice

    criteria = {square.name: square.meaning for square in squares}
    return {"square": Choice(instructions=SQUARE_INSTRUCTIONS, criteria=criteria)}


def _describe(questions: dict[str, Any]) -> dict[str, Any]:
    return {
        name: {"instructions": question.instructions, "options": dict(question.criteria)}
        for name, question in questions.items()
    }


class JevPolicy:
    # The card picked at the previous snapshot that could not be played, and when it was picked.
    _unplayed: tuple[str, float] | None = None

    def __init__(self, timeout_s: float = 2.0):
        from typesafe_sdk import RetryPolicy, TypeSafeClient

        self.client = TypeSafeClient(
            retry=RetryPolicy(max_retries=1, backoff_initial=0.1, backoff_max=0.2, timeout=timeout_s)
        )
        self.fallback = BaselinePolicy()

    def _ask(self, step: str, state: dict[str, Any], question: dict[str, Any], detail: dict[str, Any]):
        """One Jev request. Records what was asked and answered under `detail`."""
        detail["request"]["questions"].update(_describe(question))
        asked = time.time()
        answer = self.client.system_one(state, question).choices[step]
        detail["requests_made"] += 1
        detail.setdefault("step_ms", {})[step] = round(
            (time.time() - asked) * 1000
        )  # how long this step's request took
        detail[f"{step}_probabilities"] = answer.probabilities
        return answer.choice

    def _unplayed_pick(self, state: BattleState) -> dict[str, Any] | None:
        """The card picked at the previous snapshot, if it could not be played then."""
        if self._unplayed is None:
            return None
        card, picked_at = self._unplayed
        cost, ago = info(card).cost, round(state.elapsed_s - picked_at, 1)
        if cost is None or not 0 <= ago <= 10 or card not in {held.name for held in state.hand}:
            return None  # another match, a long gap, or the card has left the hand
        return {
            "card": card,
            "elixir_cost": cost,
            "more_elixir_needed_now": max(0, cost - state.elixir),
            "picked_seconds_ago": ago,
        }

    def decide(self, state: BattleState, moves: list[CardMoves]) -> Decision:
        """Three requests, each with its full option list:
        strategy (all of them) -> card (every card in hand) -> square (every square that card may go to).
        The chosen strategy is sent along as context. A card that cannot be played right now is not played."""
        started = time.time()
        sent_state = build_state(state, self._unplayed_pick(state))
        self._unplayed = None  # only the pick of the snapshot just before this one is ever reported
        detail: dict[str, Any] = {"request": {"state": sent_state, "questions": {}}, "requests_made": 0}
        chosen: HandCard | None = None
        try:
            names = {strategy.name: strategy for strategy in STRATEGIES}
            strategy = names[
                self._ask("strategy", sent_state, build_strategy_question(list(STRATEGIES)), detail)
            ]
            detail["strategy_choice"] = strategy.name
            if strategy.name in NO_PLAY:
                return Decision(None, None, "jev", detail)

            step_state = {"strategy": {"name": strategy.name, "meaning": strategy.meaning}, **sent_state}
            options = {_option(card): card for card in state.hand}
            chosen = options[self._ask("card", step_state, build_card_question(state.hand), detail)]
            detail["card_choice"] = _option(chosen)
            playable_now = {move.card.slot for move in moves}
            if chosen.slot not in playable_now:
                wait = _waiting_cost(chosen.name, state)
                self._unplayed = (chosen.name, state.elapsed_s)
                detail["note"] = f"Jev chose {chosen.name}, which cannot be played right now" + (
                    f": it needs {wait['elixir_needed']} more elixir (~{wait['seconds_until_affordable']} s)"
                    if wait
                    else ""
                )
                return Decision(None, None, "jev", detail)

            squares = {square.name: square for square in legal_squares(chosen, state)}
            if not squares:
                detail["note"] = (
                    f"Jev chose {chosen.name}, but there is no enemy troop or tower it can be cast on"
                )
                return Decision(None, None, "jev", detail)
            step_state = {"playing": _card_facts(chosen.name), **step_state}
            picked = self._ask("square", step_state, build_square_question(tuple(squares.values())), detail)
            detail["square_choice"] = picked
            return Decision(chosen, squares[picked], "jev", detail)
        except Exception as error:  # noqa: BLE001 (a lost request must never stall a live match)
            detail["error"] = repr(error)
            decision = self.fallback.decide(state, moves)
            decision.source = "fallback"
            decision.detail.update(detail)
            return decision
        finally:
            detail["latency_ms"] = round((time.time() - started) * 1000)


class BaselinePolicy:
    """No model: once elixir is healthy, play the first card into its first square.

    Used as the comparison point for JevPolicy and as its fallback when a request fails.
    """

    def __init__(self, play_at_elixir: int = 6):
        self.play_at_elixir = play_at_elixir

    def decide(self, state: BattleState, moves: list[CardMoves]) -> Decision:
        if state.elixir < self.play_at_elixir or not moves:
            return Decision(None, None, "baseline")
        return Decision(moves[0].card, moves[0].squares[0], "baseline")
