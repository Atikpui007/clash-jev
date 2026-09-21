"""Name the troops in the pictures collected with --collect, one track at a time, in the browser.

Pictures of one troop are grouped into tracks by time and position, and each track is named once.
The names are saved as DIR/labels.json: a list of {"pictures": [...], "label": "knight"}.
"""

import json
import webbrowser
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import cv2

from clash_jev.cards import info, unlocked_by
from clash_jev.units import find_units

_SAME_TROOP = 0.07  # a troop moves less than this between two pictures of it
_NEXT_PICTURE_WITHIN_S = 1.7
NOT_A_TROOP = "not_a_troop"  # a spell effect, a tower, an empty patch of grass
UNCLEAR = "unclear"  # several troops on top of each other, or too covered to tell


def _picture(path: Path) -> tuple[float, float, float]:
    stamp, x, y = path.stem.split("_")
    return int(stamp) / 1000, int(x) / 1000, int(y) / 1000


def build_tracks(folder: Path, minimum: int = 3) -> list[list[Path]]:
    """Group the collected pictures of each side into tracks of one troop, oldest first."""
    tracks: list[list[Path]] = []
    for side in ("enemy", "mine"):
        pictures = sorted((folder / side).glob("*/*.jpg"), key=lambda path: _picture(path)[0])
        open_tracks: list[list[Path]] = []
        for path in pictures:
            when, x, y = _picture(path)
            open_tracks = [
                track for track in open_tracks if when - _picture(track[-1])[0] <= _NEXT_PICTURE_WITHIN_S
            ]
            near = []
            for track in open_tracks:
                last_when, last_x, last_y = _picture(track[-1])
                if last_when < when and abs(last_x - x) <= _SAME_TROOP and abs(last_y - y) <= _SAME_TROOP:
                    near.append((abs(last_x - x) + abs(last_y - y), id(track), track))
            if near:
                min(near)[2].append(path)
            else:
                open_tracks.append([path])
                tracks.append(open_tracks[-1])
    return sorted(
        (track for track in tracks if len(track) >= minimum), key=lambda track: _picture(track[0])[0]
    )


# Easy-to-remember keys for common cards. Every other card gets the first free letter of its name.
_PREFERRED_KEYS = {
    "archers": "a", "giant": "g", "spear_goblins": "s", "knight": "k", "mini_pekka": "m", "minions": "i",
    "musketeer": "r", "goblins": "b", "goblin_cage": "c", "goblin_hut": "h", "bomber": "o", "valkyrie": "v",
    "skeletons": "e", "tombstone": "t", UNCLEAR: "u", NOT_A_TROOP: "n",
}  # fmt: skip


def _keys(choices: list[str]) -> str:
    taken: dict[str, str] = {}
    for choice in sorted(
        choices, key=lambda name: name not in _PREFERRED_KEYS
    ):  # preferred keys claim theirs first
        wanted = [
            _PREFERRED_KEYS.get(choice, ""),
            *choice.replace("_", ""),
            *"1234567890abcdefghijklmnopqrstuvwxyz",
        ]
        taken[choice] = next(key for key in wanted if key and key not in taken.values())
    return "".join(taken[choice] for choice in choices)


def shows_its_badge(path: Path) -> bool:
    """True when a level badge of the picture's own side is at the top centre. If not, the troop to name
    is not under the spotlight (it was only guessed at, or had just died)."""
    picture = cv2.imread(str(path))
    if picture is None:
        return False
    side = path.parts[-3]
    # The pictures are cut from the double-size layout, so a badge in them is twice reference size.
    return any(
        unit.owner == side and abs(unit.x - 0.5) < 0.12 and unit.y < 0.30
        for unit in find_units(picture, scale=2.0)
    )


def serve(folder: Path, arena: int | None, port: int = 8766) -> None:
    folder = folder.resolve()
    print("Looking through the pictures…", flush=True)
    every_track = build_tracks(folder)
    clear = {id(track): [path for path in track if shows_its_badge(path)] for track in every_track}
    labels_file = folder / "labels.json"
    saved = {}
    if labels_file.exists():
        saved = {entry["pictures"][0]: entry["label"] for entry in json.loads(labels_file.read_text())}
    # A track is kept when the troop is under the spotlight in at least two pictures. Tracks already
    # named stay in the list, so saved names are not lost.
    tracks = [
        track
        for track in every_track
        if len(clear[id(track)]) >= 2 or str(track[0].relative_to(folder)) in saved
    ]
    cards = sorted(
        card for card in unlocked_by(arena if arena is not None else 99) if info(card).kind != "spell"
    )
    choices = [*cards, UNCLEAR, NOT_A_TROOP]
    keys = _keys(choices)

    def relative(path: Path) -> str:
        return str(path.relative_to(folder))

    def save() -> None:
        entries = [
            {"pictures": [relative(path) for path in track], "label": saved[relative(track[0])]}
            for track in tracks
            if relative(track[0]) in saved
        ]
        labels_file.write_text(json.dumps(entries, indent=1))

    class Page(BaseHTTPRequestHandler):
        def log_message(self, *_) -> None:
            pass

        def _send(self, body: bytes, kind: str) -> None:
            self.send_response(200)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            url = urlparse(self.path)
            if url.path == "/picture":
                target = (folder / parse_qs(url.query)["p"][0]).resolve()
                if folder in target.parents and target.suffix == ".jpg":
                    return self._send(target.read_bytes(), "image/jpeg")
                return self.send_error(404)
            if url.path == "/tracks":
                data = [
                    {
                        "pictures": [relative(path) for path in (clear[id(track)] or track)],
                        "side": track[0].parts[-3],
                        "guess": Counter(path.parts[-2] for path in track).most_common(1)[0][0],
                        "label": saved.get(relative(track[0])),
                    }
                    for track in tracks
                ]
                body = json.dumps({"tracks": data, "choices": choices, "keys": keys})
                return self._send(body.encode(), "application/json")
            self._send(_PAGE.encode(), "text/html; charset=utf-8")

        def do_POST(self) -> None:
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            track = tracks[int(body["track"])]
            if body["label"] in choices:
                saved[relative(track[0])] = body["label"]
                save()
            self._send(b"{}", "application/json")

    server = ThreadingHTTPServer(("127.0.0.1", port), Page)
    print(
        f"{len(tracks)} tracks to name ({len(saved)} already named). Page: http://127.0.0.1:{port} — Ctrl+C to stop."
    )
    webbrowser.open(f"http://127.0.0.1:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print(f"Saved {len(saved)} names to {labels_file}")


_PAGE = """<!doctype html><meta charset="utf-8"><title>clash-jev · name the troops</title>
<style>
 body{margin:0;background:#12151c;color:#e8ebf2;font:15px/1.4 -apple-system,system-ui,sans-serif;padding:20px 28px}
 h1{font-size:17px;margin:0 0 4px} .meta{color:#8a93a6;margin-bottom:14px}
 #pictures{display:flex;flex-wrap:wrap;gap:6px;min-height:200px} #pictures img{width:184px;height:184px;border-radius:6px;display:block}
 .pic{position:relative;overflow:hidden;border-radius:6px}
 /* A spotlight on where the troop wearing the badge stands: right under it. Hover to see the whole picture. */
 .pic::before{content:'';position:absolute;inset:0;pointer-events:none;
   background:radial-gradient(ellipse 23% 29% at 50% 40%, transparent 96%, rgba(8,10,16,.5) 100%)}
 .pic::after{content:'';position:absolute;left:27%;top:11%;width:46%;height:58%;border:2px solid #ffd166;border-radius:50%;
   box-shadow:0 0 0 1px #0009;pointer-events:none}
 .pic:hover::before,.pic:hover::after{opacity:0}
 #choices{display:flex;flex-wrap:wrap;gap:8px;margin-top:16px}
 button{background:#1e2430;color:#e8ebf2;border:1px solid #333c4e;border-radius:8px;padding:9px 13px;font:inherit;cursor:pointer}
 button:hover{border-color:#6f8cff} button.on{background:#2a3d7a;border-color:#6f8cff} button.hint{border-color:#ffd166;box-shadow:0 0 0 1px #ffd166 inset} kbd{color:#ffd166;margin-right:7px;font:inherit;font-weight:600}
 .nav{margin-top:16px;display:flex;gap:8px;align-items:center}
</style>
<h1>Which troop is in the bright oval?</h1>
<div class="meta" id="meta"></div><div id="pictures"></div><div id="choices"></div>
<div class="nav"><button id="back">← back</button><button id="skip">skip →</button><span class="meta" id="hint">
 Name the troop in the bright oval: it is the one wearing the badge at the top of the oval. A big troop (a giant) spills outside the oval. Everything dimmed is a neighbour: ignore it. The button outlined in yellow is the troop network's guess: press Enter if it is right, otherwise press the right key. If the last pictures of a track only show a splash where the troop died, name the troop from the earlier pictures: the empty ones are dropped automatically. Hover a picture to see it undimmed. Press the key, or click.</span></div>
<script>
let data, at = 0
const el = (id) => document.getElementById(id)
function show() {
  const t = data.tracks[at], done = data.tracks.filter(x => x.label).length
  el('meta').textContent = `track ${at + 1} of ${data.tracks.length} · ${done} named · ${t.side === 'mine' ? 'YOUR troop' : 'enemy troop'}` +
    ` · ${t.pictures.length} pictures · filed as "${t.guess}"` + (done === data.tracks.length ? ' · all named — you can close this page' : '')
  const step = Math.max(1, Math.ceil(t.pictures.length / 10))
  el('pictures').innerHTML = t.pictures.filter((_, i) => i % step === 0).map(p => `<div class="pic"><img src="/picture?p=${encodeURIComponent(p)}"></div>`).join('')
  el('choices').innerHTML = data.choices.map((c, i) =>
    `<button data-c="${c}" class="${t.label === c ? 'on' : ''} ${!t.label && t.guess === c ? 'hint' : ''}"><kbd>${data.keys[i]}</kbd>${c.replaceAll('_', ' ')}${!t.label && t.guess === c ? ' · Enter' : ''}</button>`).join('')
  el('choices').querySelectorAll('button').forEach(b => b.onclick = () => choose(b.dataset.c))
}
async function choose(label) {
  data.tracks[at].label = label
  await fetch('/label', {method: 'POST', body: JSON.stringify({track: at, label})})
  const next = data.tracks.findIndex((t, i) => i > at && !t.label)
  at = next === -1 ? Math.min(at + 1, data.tracks.length - 1) : next
  show()
}
el('back').onclick = () => { at = Math.max(0, at - 1); show() }
el('skip').onclick = () => { at = Math.min(data.tracks.length - 1, at + 1); show() }
document.addEventListener('keydown', (e) => {
  if (e.key === 'ArrowLeft') return el('back').click()
  if (e.key === 'ArrowRight') return el('skip').click()
  if (e.key === 'Enter') { const g = data.tracks[at].guess; if (data.choices.includes(g)) choose(g); return }
  const i = data.keys.indexOf(e.key.toLowerCase()); if (i !== -1) choose(data.choices[i])
})
fetch('/tracks').then(r => r.json()).then(d => { data = d; const first = d.tracks.findIndex(t => !t.label); at = first === -1 ? 0 : first; show() })
</script>"""
