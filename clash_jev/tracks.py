"""Follow each troop across reads of the screen, so its name comes from every read and not only the latest.

`TroopTracker` matches the badges of each read to the troops it follows, lets every read vote on a troop's
name, and keeps a troop that went unseen for a moment. `TroopWatcher` feeds it from the device's video.
"""

import threading
import time
from collections import Counter
from dataclasses import dataclass, field, replace

from clash_jev.units import Unit

_SAME_TROOP = 0.10  # a troop moves less than this (fraction of the frame) between two reads
# A troop not seen for longer than this is gone. The badge finder and the network can both miss a troop
# that is plainly there for a read or two in a row.
_KEPT_UNSEEN_S = 1.5
_NEW_NAME_LEAD = 1.0  # a different name has to out-vote the current one by this much to replace it
# Labels for collected pictures of my own troops: a troop of mine that first appears this soon after a card
# was played, this close to where it was played, is that card. A swarm gives several such troops. The
# label never becomes the troop's name and is never sent.
_DEPLOYS_WITHIN_S = 3.0
_DEPLOYS_NEAR = 0.15


@dataclass
class _Track:
    unit: Unit
    first_seen: float
    last_seen: float
    votes: Counter = field(default_factory=Counter)
    name: str | None = None
    played_as: str | None = None

    def vote(self, name: str | None, weight: float) -> None:
        if name is None:
            return
        self.votes[name] += weight
        best, score = self.votes.most_common(1)[0]
        if self.name is None or score >= self.votes[self.name] + _NEW_NAME_LEAD or best == self.name:
            self.name = best


class TroopTracker:
    def __init__(self):
        self._tracks: list[_Track] = []
        self._played: list[tuple[str, float, float, float]] = []  # card, x, y, when
        self._lock = threading.Lock()
        self.updated_at = 0.0

    def played(self, card: str, xy: tuple[float, float], now: float) -> None:
        """Note a card of mine played at `xy`. Troops of mine that appear there next are labelled with it."""
        with self._lock:
            self._played.append((card, xy[0], xy[1], now))

    def _own_play(self, unit: Unit, now: float) -> str | None:
        self._played = [play for play in self._played if now - play[3] <= _DEPLOYS_WITHIN_S]
        near = [
            play
            for play in self._played
            if abs(unit.x - play[1]) <= _DEPLOYS_NEAR and abs(unit.y - play[2]) <= _DEPLOYS_NEAR
        ]
        return max(near, key=lambda play: play[3])[0] if near else None

    def update(self, units: tuple[Unit, ...], now: float) -> tuple[Unit, ...]:
        """Take one read of the board; return the troops being followed, named by their votes so far."""
        with self._lock:
            free = list(self._tracks)
            matched: list[_Track] = []
            pairs = sorted(
                ((abs(unit.x - track.unit.x) + abs(unit.y - track.unit.y), index, track) for index, unit in enumerate(units) for track in free if track.unit.owner == unit.owner and _near(unit, track.unit)),
                key=lambda pair: pair[0],
            )  # fmt: skip
            taken: set[int] = set()
            for _, index, track in pairs:
                if index in taken or track not in free:
                    continue
                taken.add(index)
                free.remove(track)
                track.unit, track.last_seen = units[index], now
                matched.append(track)
            for index, unit in enumerate(units):
                if index not in taken:
                    track = _Track(unit, now, now)
                    if unit.owner == "mine":
                        track.played_as = self._own_play(unit, now)
                    matched.append(track)
            for track in matched:
                track.vote(track.unit.name, track.unit.confidence or 1.0)
            self._tracks = matched + [track for track in free if now - track.last_seen <= _KEPT_UNSEEN_S]
            self.updated_at = now
            return self._snapshot(now)

    def units(self, now: float) -> tuple[Unit, ...]:
        with self._lock:
            return self._snapshot(now)

    def _snapshot(self, now: float) -> tuple[Unit, ...]:
        return tuple(
            replace(
                track.unit,
                name=track.name,
                confidence=None,
                seen_for_s=round(now - track.first_seen, 1),
                played_as=track.played_as,
                # Measured against the latest read, not the clock: a troop seen in the newest read is seen,
                # however long ago that read was.
                unseen_for_s=round(max(0.0, self.updated_at - track.last_seen), 1),
            )
            for track in self._tracks
        )


def _near(a: Unit, b: Unit) -> bool:
    return abs(a.x - b.x) <= _SAME_TROOP and abs(a.y - b.y) <= _SAME_TROOP


class TroopWatcher:
    """Reads the troops from the newest video frame every `interval` seconds, on its own thread."""

    def __init__(self, frame_source, read_troops, interval: float = 0.25):
        self.tracker = TroopTracker()
        self._frame_source = frame_source
        self._read_troops = read_troops
        self._interval = interval
        self.reads = 0
        threading.Thread(target=self._watch, daemon=True).start()

    def _watch(self) -> None:
        while True:
            started = time.time()
            try:
                self.tracker.update(self._read_troops(self._frame_source()), started)
                self.reads += 1
            except Exception as error:  # noqa: BLE001 (a bad frame must not end the watching)
                print(f"troop watcher skipped a frame ({error!r})", flush=True)
            time.sleep(max(0.02, self._interval - (time.time() - started)))

    def units(self, max_age_s: float = 1.0) -> tuple[Unit, ...] | None:
        """The troops being followed, or None when the watcher has not managed a read lately."""
        now = time.time()
        if now - self.tracker.updated_at > max_age_s:
            return None
        return self.tracker.units(now)
