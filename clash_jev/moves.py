"""get_valid_moves: which ready, affordable cards can go to which squares.

A Square is a named spot on the arena ("left_bridge") with the screen point to tap, as a fraction of the
frame. Troops and buildings go on your half. A spell is cast on an enemy tower or troop, so its squares
are built from the board.
"""

from dataclasses import dataclass

from clash_jev.cards import Kind, base_name, info
from clash_jev.state import BattleState, HandCard


@dataclass(frozen=True)
class Square:
    name: str
    xy: tuple[float, float]
    meaning: str


def _pair(name: str, left_x: float, y: float, meaning: str) -> list[Square]:
    return [
        Square(f"left_{name}", (left_x, y), f"Left lane: {meaning}"),
        Square(f"right_{name}", (1 - left_x, y), f"Right lane: {meaning}"),
    ]


# A square's meaning says only where it is, in tiles.
BRIDGE = _pair(
    "bridge",
    0.28,
    0.475,
    "on your side at the foot of the bridge, 1 tile from the river. About 6 tiles in front of your princess "
    "tower in this lane and 12 tiles from the enemy's.",
)
TOWER_FRONT = _pair(
    "tower_front",
    0.36,
    0.545,
    "on your side, about 3 tiles in front of your princess tower in this lane and 2 tiles toward the middle. "
    "About 4 tiles from the river.",
)
BACK = _pair(
    "back",
    0.17,
    0.735,
    "the back corner of your side, about 6 tiles behind your princess tower in this lane, beside your king "
    "tower. About 13 tiles from the river and 24 tiles from the enemy's princess tower.",
)
CENTRE = [
    Square(
        "centre",
        (0.50, 0.475),
        "Middle of your side, 1 tile from the river, midway between the two bridges. About 8 tiles from each of "
        "your princess towers.",
    ),
    Square(
        "centre_king_front",
        (0.50, 0.54),
        "Middle of your side, between the two lanes, about 7 tiles in front of your king tower and 4 tiles from "
        "the river. About 6 tiles from each of your princess towers.",
    ),
]
ENEMY_TOWER = _pair("enemy_tower", 0.28, 0.22, "on the enemy princess tower of this lane.")
# Opens once the enemy princess tower on that side has fallen.
POCKET = _pair(
    "pocket",
    0.28,
    0.315,
    "on the enemy side, where their destroyed princess tower stood, about 10 tiles from their king tower.",
)

_OWN_HALF = BRIDGE + TOWER_FRONT + BACK + CENTRE

# Spell targets depend on the board, so they are worked out per state in spell_targets().
ENEMY_KING = Square("enemy_king_tower", (0.50, 0.125), "on the enemy king tower.")
_MY_SIDE_Y = 0.445  # a troop whose badge is below this is on your half of the arena
_TROOP_BELOW_BADGE = 0.03

_SQUARES_BY_KIND: dict[Kind, list[Square]] = {
    "troop": _OWN_HALF,
    "building": TOWER_FRONT + CENTRE[1:],  # a building goes where it can be reached from both lanes
    "spell": [],  # see spell_targets()
    "anywhere_troop": ENEMY_TOWER + _OWN_HALF,
}
# The few spells that cannot be cast on the enemy half.
_OWN_HALF_ONLY_SPELLS = {"royal_delivery"}
ALL_SQUARES = {square.name: square for square in [*_OWN_HALF, *ENEMY_TOWER, ENEMY_KING, *POCKET]}


@dataclass(frozen=True)
class CardMoves:
    card: HandCard
    squares: tuple[Square, ...]


def playable(card: HandCard, elixir: int) -> bool:
    cost = info(card.name).cost
    return card.ready and (cost is None or cost <= elixir)


def spell_targets(card: HandCard, state: BattleState) -> tuple[Square, ...]:
    """Everything of the enemy's a spell can be cast on right now: their standing towers, and each of
    their troops at the spot where it stands."""
    standing = [
        tower
        for tower, health in zip(ENEMY_TOWER, (state.towers.enemy_left, state.towers.enemy_right))
        if health != 0
    ]
    targets = [*standing, ENEMY_KING]
    own_half_only = base_name(card.name) in _OWN_HALF_ONLY_SPELLS
    if own_half_only:
        targets = []  # cannot be cast on the enemy half at all, so towers are out of reach
    for index, unit in enumerate(unit for unit in state.units if unit.owner == "enemy"):
        if own_half_only and unit.y < _MY_SIDE_Y:
            continue
        lane = "left" if unit.x < 0.5 else "right"
        where = (
            "on their side" if unit.y < 0.37 else "at the bridge" if unit.y < _MY_SIDE_Y else "on your side"
        )
        troop = (unit.name or "unidentified troop").replace("_", " ")
        targets.append(
            Square(
                f"enemy_{unit.name or 'troop'}_{lane}_{index}",
                (unit.x, min(0.78, unit.y + _TROOP_BELOW_BADGE)),
                f"on the enemy {troop} in the {lane} lane, {where}.",
            )
        )
    return tuple(targets)


def legal_squares(card: HandCard, state: BattleState) -> tuple[Square, ...]:
    """Where this card may be placed. Placement rules only, affordability is not checked."""
    kind = info(card.name).kind
    if kind == "spell":
        return spell_targets(card, state)
    squares = list(_SQUARES_BY_KIND[kind])
    if kind in ("troop", "building"):
        if state.towers.enemy_left == 0:
            squares.append(POCKET[0])
        if state.towers.enemy_right == 0:
            squares.append(POCKET[1])
    return tuple(squares)


def get_valid_moves(state: BattleState) -> list[CardMoves]:
    """Every card that can physically be played right now, with the squares it may go to."""
    return [
        CardMoves(card, legal_squares(card, state))
        for card in state.hand
        # An unidentified card has no known kind or cost, so it cannot be offered a legal placement.
        if card.name != "unknown" and playable(card, state.elixir)
    ]
