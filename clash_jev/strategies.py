"""Strategies: the first pick of each step, from one fixed list that is always offered in full.

The pick is passed to the card and square questions as context. It filters nothing.

    state -> STRATEGIES -> pick one -> pick a card from the hand -> pick a legal square
"""

from dataclasses import dataclass

SAVE = "save_elixir"
HOLD = "hold_elixir_for_threat"


@dataclass(frozen=True)
class Strategy:
    name: str
    meaning: str
    lane: str | None = None
    not_for: str | None = None  # when this strategy does not apply (TypeSafe structured criteria)


_AT_CAP = (
    "When you already hold 10 elixir: elixir caps at 10, so any further elixir is wasted. Do not leak elixir."
)


def _lane(side: str) -> list[Strategy]:
    return [
        Strategy(
            f"defend_{side}",
            f"Enemy units in the {side} lane are close to your {side} princess tower, or to your king tower once "
            "that princess tower has fallen: on your side of the river or about to cross it, walking toward the "
            f"tower or already hitting it. Play a card against them, in the {side} lane.",
            side,
            not_for=(
                f"When no enemy unit in the {side} lane is close to your tower (`tiles_from_my_tower` is the "
                "distance of each): units that are still far away on the enemy's side are not attacking it yet. "
                "Also when you mean to draw the attackers to the middle of your side: that is defend_centre."
            ),
        ),
        Strategy(
            f"counter_push_{side}",
            f"Units of your own are already in the {side} lane, typically the survivors of a defence. Add to them, "
            f"so that together they go on to attack the enemy's {side} tower.",
            side,
            not_for=(
                f"When you have no units of your own in the {side} lane: with nothing there to add to, an attack "
                f"in that lane is push_{side}."
            ),
        ),
        Strategy(
            f"push_{side}",
            f"Start a new attack in the {side} lane now, aimed at the enemy's {side} princess tower, or at their "
            "king tower once that princess tower has fallen.",
            side,
            not_for=(
                "When you mean to start from the back of your side and let your forces gather before they reach the "
                "enemy: that is build_push."
            ),
        ),
    ]


# `meaning` says what a strategy is. `not_for` says where it stops being that strategy and which one
# it turns into.
STRATEGIES: tuple[Strategy, ...] = (
    Strategy(
        SAVE,
        "Play nothing now. Let your elixir build up, so that a bigger play of your own becomes possible at a "
        "later snapshot.",
        not_for=(
            "When you already hold 10 elixir: there it is the worst choice. Elixir caps at 10, so nothing more can "
            "be saved and any further elixir is wasted. Do not leak elixir. Also when the elixir is being kept to "
            "answer enemy units: that is hold_elixir_for_threat."
        ),
    ),
    Strategy(
        HOLD,
        "Play nothing now, because of a threat: keep your elixir in reserve for an attack the opponent is "
        "preparing, or wait until you can play the card that answers best an attack that is already under way.",
        not_for=(
            _AT_CAP + " Also when there is no enemy attack to answer, neither under way nor being prepared: "
            "keeping elixir for a play of your own is save_elixir."
        ),
    ),
    *(strategy for pair in zip(_lane("left"), _lane("right")) for strategy in pair),
    Strategy(
        "defend_centre",
        "Enemy units are coming down a lane toward one of your towers, and you play a card in the middle of your "
        "side, between the two lanes, so that they leave their lane and come to it: there both of your princess "
        "towers can shoot at them. It is mainly melee units that are drawn over this way, since they walk to "
        "whatever they attack.",
        not_for=(
            "When no enemy unit is close to any of your towers (`tiles_from_my_tower` is the distance of each). "
            "Also when you mean to meet the attackers in the lane they are in: that is defend_left or defend_right."
        ),
    ),
    Strategy(
        "build_push",
        "Start a slow attack from the very back of your own side. It takes many seconds to reach the enemy, and "
        "during them your elixir refills and more of your forces can join it.",
        not_for=(
            "When you mean the attack to reach the enemy right away rather than gather on the way: that is "
            "push_left or push_right."
        ),
    ),
    Strategy(
        "split_push",
        "Attack in both lanes within the same stretch of play, so that the opponent has to divide their defence "
        "between two towers.",
        not_for="When one lane is all you mean to attack: that is push_left or push_right.",
    ),
    Strategy(
        "cycle",
        "Change what is in your hand: play one of the cards you hold so that the card shown as `next_card` "
        "takes its place. It is about which card leaves your hand and which one arrives, not about the board.",
        not_for="When the card you want to use is already in your hand.",
    ),
)
NO_PLAY = {SAVE, HOLD}
