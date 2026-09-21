"""extract_state: screenshot -> BattleState.

Elixir, troops and tower health are read here. Hand cards are read in hand.py. Positions are
fractions of the frame, measured on a 419x633 battle screenshot.
"""

import os
import time
from collections import Counter
from dataclasses import dataclass

import cv2
import numpy

from clash_jev.collect import save_troops
from clash_jev.hand import HandReader
from clash_jev.opponent import OpponentElixir
from clash_jev.screenmap import REFERENCE, ScreenMap
from clash_jev.state import BattleState, LaneView, Towers
from clash_jev.tracks import TroopTracker, TroopWatcher
from clash_jev.troops import TroopClassifier
from clash_jev.units import Unit, find_units

_TROOP_SCALE = 2
_TROOP_BELOW_BADGE = 0.03  # a troop stands roughly this far below its level badge


@dataclass(frozen=True)
class Layout:
    elixir_y: float = 0.968
    elixir_x: tuple[float, ...] = (0.356, 0.394, 0.449, 0.506, 0.573, 0.625, 0.685, 0.749, 0.809, 0.869)
    elixir_bgr: tuple[int, int, int] = (240, 137, 244)
    elixir_tolerance: int = 65
    arena: tuple[float, float, float, float] = (0.13, 0.09, 0.87, 0.79)  # x0, y0, x1, y1
    bridge_band: tuple[float, float] = (0.40, 0.475)  # y range counted as "at the bridge"
    # Health-bar strip of each princess tower: x0, y0, x1, y1.
    tower_bars: tuple[tuple[str, tuple[float, float, float, float]], ...] = (
        ("enemy_left", (0.20, 0.139, 0.36, 0.163)),
        ("enemy_right", (0.64, 0.139, 0.80, 0.163)),
        ("my_left", (0.20, 0.612, 0.36, 0.636)),
        ("my_right", (0.64, 0.612, 0.80, 0.636)),
    )
    # King bars appear beside the king's level badge after the first hit: x0, y0, x1, y1.
    king_bars: tuple[tuple[str, tuple[float, float, float, float]], ...] = (
        ("enemy_king", (0.40, 0.005, 0.75, 0.075)),
        ("my_king", (0.40, 0.735, 0.75, 0.80)),
    )
    tower_bar_width: float = 39 / 419  # a full bar, as a fraction of frame width
    tower_missing_s: float = 4.0  # bar absent for this long without a break = tower destroyed


# Filled part of a tower bar: (hue range, min saturation, min value) in OpenCV HSV.
_TOWER_BAR_COLOUR = {"enemy": ((168, 174), 190, 190), "my": ((98, 102), 125, 225)}


def to_reference(frame: numpy.ndarray) -> numpy.ndarray:
    """Colour thresholds and badge sizes are exact on the reference layout, so read everything there."""
    return ScreenMap.for_frame(frame).to_reference(frame)


class Perception:
    def __init__(self, layout: Layout | None = None, watcher: TroopWatcher | None = None):
        self.layout = layout or Layout()
        self.watcher = (
            watcher  # follows the troops several times a second; without one, each snapshot is a read
        )
        self.tracker = TroopTracker()
        self._tower_missing_since: dict[str, float] = {}
        self._tower_last: dict[str, float] = {}  # last health read per princess tower
        self._king_full: dict[str, int] = {}  # widest bar seen per king = its full health
        self._tower_full: dict[str, float] = {}  # widest bar seen per princess tower
        self._full_since: float | None = None  # elapsed time at which elixir reached 10
        self.hand_reader = HandReader()  # also reads the Next card
        self.opponent = OpponentElixir()
        arena = os.environ.get("CLASH_JEV_ARENA")  # set by --arena: the cards an opponent can own
        self.identifier = (
            TroopClassifier(int(arena) if arena else None) if TroopClassifier.available() else None
        )

    def read_elixir(self, frame: numpy.ndarray) -> int:
        lay, (height, width) = self.layout, frame.shape[:2]
        row = frame[min(height - 1, int(lay.elixir_y * height))]
        elixir = 0
        for amount, x in enumerate(lay.elixir_x, start=1):
            if numpy.abs(row[int(x * width)].astype(int) - lay.elixir_bgr).max() <= lay.elixir_tolerance:
                elixir = amount
        return elixir

    def read_units(self, frame: numpy.ndarray) -> tuple[Unit, ...]:
        x0, y0, x1, y1 = self.layout.arena
        ignore = [box for _, box in self.layout.tower_bars]
        units = find_units(frame, ignore)
        return tuple(unit for unit in units if x0 <= unit.x <= x1 and y0 <= unit.y <= y1)

    def read_lane(self, units: tuple[Unit, ...], lane: str) -> LaneView:
        counts: Counter[str] = Counter()
        top, bottom = self.layout.bridge_band
        for unit in units:
            if (unit.x < 0.5) != (lane == "left"):
                continue
            y = unit.y + _TROOP_BELOW_BADGE
            where = "on_their_side" if y < top else "at_bridge" if y < bottom else "on_my_side"
            counts[f"{unit.owner}_{where}"] += 1
        return LaneView(**counts)

    @staticmethod
    def _bar_pixels(hsv: numpy.ndarray, name: str, box: tuple[float, float, float, float]) -> int:
        """Longest lit run of tower-bar colour on any row of the strip."""
        height, width = hsv.shape[:2]
        x0, y0, x1, y1 = box
        (low, high), min_saturation, min_value = _TOWER_BAR_COLOUR[name.split("_")[0]]
        strip = hsv[int(y0 * height) : int(y1 * height), int(x0 * width) : int(x1 * width)]
        lit = (
            (strip[..., 0] >= low)
            & (strip[..., 0] <= high)
            & (strip[..., 1] >= min_saturation)
            & (strip[..., 2] >= min_value)
        )
        return int(lit.sum(axis=1).max()) if lit.size else 0

    def read_towers(self, frame: numpy.ndarray) -> Towers:
        width, now = frame.shape[1], time.time()
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        health: dict[str, float | None] = {}
        for name, box in self.layout.king_bars:
            filled = self._bar_pixels(hsv, name, box)
            if filled >= 4:
                self._king_full[name] = max(self._king_full.get(name, 0), filled)
                health[name] = round(filled / self._king_full[name], 2)
            else:
                health[name] = 1.0 if name not in self._king_full else None
        for name, box in self.layout.tower_bars:
            filled = self._bar_pixels(hsv, name, box)
            if filled >= 2:
                self._tower_missing_since.pop(name, None)
                # A full bar's width varies by a few pixels with the screen shape, so "full" is the widest
                # this tower's bar has been seen, and never less than most of the nominal width
                # (a tower first seen already damaged must not read as full).
                nominal = self.layout.tower_bar_width * width
                self._tower_full[name] = max(self._tower_full.get(name, 0.0), filled, 0.9 * nominal)
                health[name] = self._tower_last[name] = round(min(1.0, filled / self._tower_full[name]), 2)
                continue
            # A bar can be hidden for a moment: by a spell effect, or when a tower is so low that the health
            # number printed over the bar covers what is left of the fill. Only a bar that stays gone is a
            # dead tower. Until then the tower keeps its last reading.
            missing_for = now - self._tower_missing_since.setdefault(name, now)
            gone = missing_for >= self.layout.tower_missing_s
            health[name] = 0.0 if gone else self._tower_last.get(name)
        return Towers(**health)

    def extract_state(self, frame: numpy.ndarray, elapsed_s: float = 0.0) -> BattleState:
        screen = ScreenMap.for_frame(frame)
        # Troops are read on a double-size drawing of the layout: their badges and sprites are small, and
        # the device frame holds more detail than 419 columns keep. Positions are fractions in both.
        detailed = screen.to_reference(frame, scale=_TROOP_SCALE if frame.shape[1] > REFERENCE[0] else 1)
        frame = screen.to_reference(frame)
        hand = self.hand_reader.read(frame)
        units = self.watcher.units() if self.watcher is not None else None
        if units is None:
            units = self.tracker.update(self._read_troops(detailed), time.time())
        save_troops(detailed, hand, units)
        return self._assemble(frame, elapsed_s, hand, units)

    def played(self, card: str, xy: tuple[float, float]) -> None:
        """Tell whoever follows the troops that a card of mine was just played at `xy`."""
        tracker = self.watcher.tracker if self.watcher is not None else self.tracker
        tracker.played(card, xy, time.time())

    def read_troops(self, frame: numpy.ndarray) -> tuple[Unit, ...]:
        """One read of the troops on a device frame: what a TroopWatcher calls, several times a second."""
        screen = ScreenMap.for_frame(frame)
        # Troops are only named while a battle is on screen, which a hand of cards shows: a menu has
        # badge-coloured shapes of its own.
        hand = self.hand_reader.read(screen.to_reference(frame))
        in_battle = sum(card.name != "unknown" for card in hand) >= 2
        return self._read_troops(
            screen.to_reference(frame, scale=_TROOP_SCALE if frame.shape[1] > REFERENCE[0] else 1),
            identify=in_battle,
        )

    def _read_troops(self, detailed: numpy.ndarray, identify: bool = True) -> tuple[Unit, ...]:
        units = self.read_units(detailed)
        if self.identifier is not None and identify:
            units = self.identifier.name_units(detailed, units)
        return units

    def _assemble(self, frame, elapsed_s, hand, units) -> BattleState:
        rate = BattleState(elapsed_s=elapsed_s, elixir=0, hand=hand).elixir_rate
        elixir = self.read_elixir(frame)
        if elixir < 10:
            self._full_since = None
        elif self._full_since is None:
            self._full_since = elapsed_s
        return BattleState(
            elapsed_s=elapsed_s,
            elixir=elixir,
            seconds_at_full_elixir=0.0
            if self._full_since is None
            else round(elapsed_s - self._full_since, 1),
            hand=hand,
            left=self.read_lane(units, "left"),
            right=self.read_lane(units, "right"),
            towers=self.read_towers(frame),
            units=units,
            enemy_elixir_estimate=self.opponent.update(elapsed_s, rate, units),
            next_card=self.hand_reader.next_card,
        )
