"""BattleState: what one screenshot says about the match. Observed facts only."""

from dataclasses import dataclass
from typing import Literal

from clash_jev.units import Unit

ElixirRate = Literal["single", "double", "triple"]


@dataclass(frozen=True)
class HandCard:
    slot: int  # 0-3, left to right
    name: str  # card id as in cards.py ("mini_pekka"), or "unknown"
    ready: bool  # drawn in full colour: the game will accept this card now


@dataclass(frozen=True)
class LaneView:
    """How many troops are in one lane, by owner and by where they stand."""

    enemy_on_my_side: int = 0
    enemy_at_bridge: int = 0
    enemy_on_their_side: int = 0
    mine_on_my_side: int = 0
    mine_at_bridge: int = 0
    mine_on_their_side: int = 0


@dataclass(frozen=True)
class Towers:
    """Tower health, 0-1. 0.0 = destroyed. None = not read this frame.

    A king tower draws no bar until it is first hit, so an unseen king bar reads 1.0.
    """

    enemy_left: float | None = None
    enemy_right: float | None = None
    enemy_king: float | None = None
    my_left: float | None = None
    my_right: float | None = None
    my_king: float | None = None


@dataclass(frozen=True)
class BattleState:
    elapsed_s: float
    elixir: int
    hand: tuple[HandCard, ...]
    left: LaneView = LaneView()
    right: LaneView = LaneView()
    towers: Towers = Towers()
    units: tuple[Unit, ...] = ()
    enemy_elixir_estimate: float | None = None  # tracked, never observed: see opponent.py
    snapshot_interval_s: float = 1.0  # how often a new snapshot is taken and a request is made
    seconds_at_full_elixir: float = 0.0  # how long elixir has sat at 10
    next_card: str | None = None  # the card showing as "Next": it takes the slot of whatever you play

    @property
    def seconds_per_elixir(self) -> float:
        """How long one elixir takes to arrive at the current rate."""
        return {"single": 2.8, "double": 1.4, "triple": 0.93}[self.elixir_rate]

    @property
    def elixir_rate(self) -> ElixirRate:
        if self.elapsed_s < 120:
            return "single"
        if self.elapsed_s < 240:
            return "double"
        return "triple"
