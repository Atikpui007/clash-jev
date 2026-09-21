"""Collected pictures are grouped into tracks of one troop, which are named once each."""

import cv2
import numpy

from clash_jev.label import build_tracks


def _save(folder, side, name, stamp, x, y):
    target = folder / side / name
    target.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(target / f"{stamp}_{x}_{y}.jpg"), numpy.zeros((8, 8, 3), numpy.uint8))


def test_pictures_a_second_apart_and_close_together_are_one_track(tmp_path):
    for step in range(4):  # one enemy troop walking down, filed under two different guesses
        _save(
            tmp_path, "enemy", "knight" if step < 2 else "giant", 1000_000 + step * 1000, 300, 200 + step * 12
        )
    for step in range(3):  # another enemy troop at the same time, far away
        _save(tmp_path, "enemy", "minions", 1000_000 + step * 1000, 700, 300)
    for step in range(3):  # my troop on the same spot as the first: never the same track
        _save(tmp_path, "mine", "unnamed", 1000_000 + step * 1000, 300, 200 + step * 12)
    _save(
        tmp_path, "enemy", "goblins", 1000_000 + 9000, 300, 236
    )  # same spot, much later: a new troop, too short
    tracks = build_tracks(tmp_path)
    assert sorted(len(track) for track in tracks) == [3, 3, 4]
    walking = next(track for track in tracks if len(track) == 4)
    assert {path.parts[-2] for path in walking} == {"knight", "giant"} and walking[0].parts[-3] == "enemy"


def test_label_keys_are_easy_to_remember_and_never_clash():
    from clash_jev.cards import CARDS
    from clash_jev.label import NOT_A_TROOP, UNCLEAR, _keys

    arena_1 = ["archers", "giant", "goblin_cage", "goblin_hut", "goblins", "knight", "mini_pekka", "minions"]
    arena_1 += ["musketeer", "spear_goblins", UNCLEAR, NOT_A_TROOP]
    assert _keys(arena_1) == "agchbkmirsun"
    assert not any(key.isdigit() for key in _keys(arena_1))  # a digit gets pressed for the badge's number
    assert (
        _keys(["bomber", "goblins", "valkyrie", "skeletons", "tombstone"]) == "obvet"
    )  # arena 2 keeps arena 1's keys
    troops = sorted(name for name, card in CARDS.items() if card.kind != "spell")[
        :34
    ]  # as many as there are keys
    keys = _keys([*troops, UNCLEAR, NOT_A_TROOP])
    assert len(set(keys)) == len(keys) == len(troops) + 2
