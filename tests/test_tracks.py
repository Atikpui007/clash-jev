"""Troops followed from read to read: names decided by vote, brief disappearances bridged."""

import time

from clash_jev.tracks import TroopTracker, TroopWatcher
from clash_jev.units import Unit


def _enemy(x, y, name=None, confidence=None):
    return Unit("enemy", x, y, None, name, confidence)


def test_one_wrong_read_is_outvoted_and_a_missed_read_keeps_the_name():
    tracker = TroopTracker()
    for step in range(4):
        (troop,) = tracker.update((_enemy(0.30, 0.20 + step * 0.01, "knight", 0.8),), now=step * 0.25)
    assert troop.name == "knight"
    (troop,) = tracker.update((_enemy(0.30, 0.25, "giant", 0.9),), now=1.0)  # one bad frame
    assert troop.name == "knight" and troop.seen_for_s == 1.0
    (troop,) = tracker.update(
        (_enemy(0.30, 0.26),), now=1.25
    )  # the network was not sure this time: the name stays
    assert troop.name == "knight" and (troop.x, troop.y) == (0.30, 0.26)
    for step in range(4):  # it really is a giant after all: enough reads change the name
        (troop,) = tracker.update((_enemy(0.30, 0.27, "giant", 0.9),), now=1.5 + step * 0.25)
    assert troop.name == "giant"


def test_a_hidden_troop_is_kept_briefly_then_dropped_and_owners_never_mix():
    tracker = TroopTracker()
    tracker.update((_enemy(0.30, 0.20, "knight", 0.8), Unit("mine", 0.32, 0.21, None)), now=0.0)
    kept = tracker.update((Unit("mine", 0.32, 0.22, None),), now=0.25)  # a spell effect hides the enemy badge
    assert sorted(unit.owner for unit in kept) == ["enemy", "mine"]
    assert (
        next(unit for unit in kept if unit.owner == "mine").name is None
    )  # my troop did not inherit "knight"
    assert (
        len(tracker.update((Unit("mine", 0.32, 0.23, None),), now=1.0)) == 2
    )  # still bridged after a second
    assert [unit.owner for unit in tracker.update((Unit("mine", 0.32, 0.24, None),), now=2.0)] == ["mine"]


def test_two_troops_side_by_side_keep_their_own_names():
    tracker = TroopTracker()
    for step in range(3):
        y = 0.20 + step * 0.01
        units = tracker.update(
            (_enemy(0.30, y, "knight", 0.8), _enemy(0.36, y, "archers", 0.8)), now=step * 0.25
        )
    assert sorted((unit.x, unit.name) for unit in units) == [(0.30, "knight"), (0.36, "archers")]


def test_the_watcher_reads_several_times_a_second_and_goes_stale_when_it_cannot():
    frames = iter(range(1000))
    watcher = TroopWatcher(
        lambda: next(frames), lambda frame: (_enemy(0.30, 0.20, "knight", 0.8),), interval=0.02
    )
    deadline = time.time() + 2
    while watcher.reads < 5 and time.time() < deadline:
        time.sleep(0.01)
    assert watcher.reads >= 5
    (troop,) = watcher.units()
    assert troop.name == "knight" and troop.confidence is None
    assert watcher.units(max_age_s=-1) is None  # too old to trust: the caller reads the frame itself


def test_my_own_plays_label_my_troops_for_collection_but_never_name_them():
    tracker = TroopTracker()
    tracker.played("knight", (0.28, 0.475), now=10.0)  # left bridge
    before = tracker.update((Unit("mine", 0.70, 0.60, None),), now=10.2)  # already on the board, far away
    assert before[0].played_as is None
    units = tracker.update((Unit("mine", 0.70, 0.60, None), Unit("mine", 0.29, 0.45, None)), now=11.0)
    assert sorted((unit.x, unit.played_as) for unit in units) == [(0.29, "knight"), (0.70, None)]
    assert all(unit.name is None for unit in units)  # the name comes from sight alone
    units = tracker.update((Unit("mine", 0.70, 0.59, None), Unit("mine", 0.29, 0.40, 0.8)), now=12.0)
    assert {unit.played_as for unit in units if unit.x < 0.5} == {
        "knight"
    }  # the label follows it as it walks
    late = tracker.update(
        (*units, Unit("mine", 0.27, 0.47, None)), now=20.0
    )  # long after the play: not that card
    assert [unit.played_as for unit in late if unit.y == 0.47] == [None]
    assert (
        tracker.update((Unit("enemy", 0.28, 0.46, None),), now=20.1)[-1].played_as is None
    )  # never an enemy


def test_a_troop_that_is_only_remembered_says_so():
    tracker = TroopTracker()
    (seen,) = tracker.update((_enemy(0.30, 0.20, "knight", 0.8),), now=0.0)
    (remembered,) = tracker.update((), now=0.5)  # it died or was hidden: kept for a moment, but not seen
    assert seen.unseen_for_s == 0.0 and remembered.unseen_for_s == 0.5
    (later,) = tracker.units(now=0.7)  # asked a moment after the last read: still the same answer
    assert later.unseen_for_s == 0.5
    (fresh,) = tracker.update((_enemy(0.30, 0.21, "knight", 0.8),), now=1.0)
    assert (
        tracker.units(now=1.3)[0].unseen_for_s == 0.0 == fresh.unseen_for_s
    )  # seen in the newest read: photographed
