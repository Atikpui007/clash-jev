"""A recorded run is turned into a replay: the briefing stored once, the results screen left out."""

import json

from clash_jev.publish import publish


def _row(elapsed, hand, action="wait", towers=None, **extra):
    state = {"hand": [{"name": name} for name in hand], "units": [], "towers": towers or {}}
    sent = {"game": {"name": "Clash Royale"}, "elixir": 5, "hand": []}
    questions = {"strategy": {"instructions": "Pick a strategy.", "options": {"save_elixir": "…"}}}
    return {"state_elapsed": elapsed, "state": state, "action": action, "source": "jev", "requests_made": 1,
            "request": {"state": sent, "questions": questions}, **extra}  # fmt: skip


def test_publish_keeps_the_match_and_drops_the_results_screen(tmp_path):
    standing = dict.fromkeys(
        ("enemy_left", "enemy_right", "enemy_king", "my_left", "my_right", "my_king"), 1.0
    )
    rows = [
        _row(1.0, ["knight", "giant", "archers", "minions"], towers=standing),
        _row(
            9.0,
            ["knight", "giant", "archers", "minions"],
            action="knight -> left_bridge",
            requests_made=3,
            towers={**standing, "enemy_left": 0.0},
            step_ms={"strategy": 140, "card": 120, "square": 110},
        ),
        _row(
            14.0, ["unknown"] * 4, towers=dict.fromkeys(standing, 0.0)
        ),  # the results screen: a meaningless reading
    ]
    log = tmp_path / "20260101-120000-jev.jsonl"
    log.write_text("\n".join(json.dumps(row) for row in rows))

    summary = publish(log, tmp_path / "site", title="A test match")
    assert summary == {
        "id": "20260101-120000", "title": "A test match", "seconds": 11.0, "decisions": 2, "plays": 1, "requests": 4,
        "towers_destroyed": 1, "towers_lost": 0, "has_video": False,
    }  # fmt: skip
    replay = json.loads((tmp_path / "site" / "20260101-120000" / "replay.json").read_text())
    assert replay["briefing"] == {"name": "Clash Royale"} and replay["questions"] == {
        "strategy": "Pick a strategy."
    }
    assert all("game" not in decision["state"] for decision in replay["decisions"])
    assert replay["decisions"][1]["step_ms"]["card"] == 120
    assert [entry["id"] for entry in json.loads((tmp_path / "site" / "index.json").read_text())] == [
        "20260101-120000"
    ]


def test_the_results_screen_is_not_part_of_the_match():
    from clash_jev.publish import _in_battle

    def row(*names):
        return {"state": {"hand": [{"name": name} for name in names]}}

    assert _in_battle(row("giant", "arrows", "unknown", "fireball"))
    assert not _in_battle(row("fireball", "unknown", "unknown", "unknown"))
    assert not _in_battle(row("fireball", "fireball", "unknown", "unknown"))  # one card read in two slots
