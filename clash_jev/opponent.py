"""Estimate the opponent's elixir, which is never shown on screen.

Both sides start at 5 and refill at the same clock-driven rate. Each new enemy troop costs the opponent its
card cost if the troop is identified, otherwise an average card. Spells leave no troop, so the estimate
runs high.
"""

from clash_jev.cards import info
from clash_jev.units import Unit

START_ELIXIR = 5.0
MAX_ELIXIR = 10.0
SECONDS_PER_ELIXIR = 2.8
AVERAGE_CARD_COST = 3.8
_SAME_TROOP = 0.10  # a troop moves less than this (fraction of the frame) between two reads
_SAME_CARD = 0.09  # badges this close that appear together came from one card (a swarm)
_RATE = {"single": 1, "double": 2, "triple": 3}


def _near(a: Unit, b: Unit, limit: float) -> bool:
    return abs(a.x - b.x) <= limit and abs(a.y - b.y) <= limit


class OpponentElixir:
    def __init__(self):
        self.elixir = START_ELIXIR
        self._last_elapsed = 0.0
        self._known: list[Unit] = []

    def update(self, elapsed_s: float, elixir_rate: str, units: tuple[Unit, ...]) -> float:
        self.elixir += max(0.0, elapsed_s - self._last_elapsed) * _RATE[elixir_rate] / SECONDS_PER_ELIXIR
        self.elixir = min(MAX_ELIXIR, self.elixir)
        self._last_elapsed = elapsed_s

        enemies = [unit for unit in units if unit.owner == "enemy"]
        arrived = [
            unit for unit in enemies if not any(_near(unit, known, _SAME_TROOP) for known in self._known)
        ]
        cards: list[list[Unit]] = []
        for unit in arrived:
            group = next(
                (card for card in cards if any(_near(unit, other, _SAME_CARD) for other in card)), None
            )
            if group is None:
                cards.append([unit])
            else:
                group.append(unit)
        for card in cards:
            cost = next((info(unit.name).cost for unit in card if unit.name and info(unit.name).cost), None)
            self.elixir = max(0.0, self.elixir - (cost or AVERAGE_CARD_COST))

        self._known = enemies
        return round(self.elixir, 1)
