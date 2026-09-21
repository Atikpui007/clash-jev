# clash-jev

I got early access to Jev, [TypeSafe AI](https://typesafe.ai)'s new System One model, and decided to
play around with it. I built clash-jev, a bot that uses Jev to make near real-time decisions on live
game data. It plays Clash Royale on a real Android device.

Jev does not generate text. A request carries a state and a question with a fixed set of options,
and Jev returns the option it chose with a probability for every option, in about 135 milliseconds.
Jev accepts text only, so most of this project is the computer vision that turns live video into a
JSON game state.

How it works:

- The device streams its screen to the laptop as H.264 video over `adb`.
- OpenCV reads the hand, the elixir and the towers. A small network that I trained on pictures I
  labelled by hand names the troops.
- Once a second the readings become one JSON game state.
- Jev picks a strategy, then a card, then a square.
- The bot checks that the play is physically possible and taps it.
- The bot logs every decision next to a synced video.

Nothing is trained to play. The bot uses no reinforcement learning and no simulator.

The [engineering write-up](https://bytelabs-oss.github.io/clash-jev/) has the architecture diagram and
covers each stage with the technical choices behind it.

```python
state = extract_state(screenshot)
options = get_valid_moves(state)
move = choose_with_jev(state, options)
click_card(device, screenshot, move.card.slot)
click_square(device, screenshot, move.square)
```

These five functions are in `clash_jev/pipeline.py`.

You can watch recorded matches at https://clash-jev.vercel.app. Each replay shows the video, what the
bot read, and every question Jev was asked.

> **Research project.** Automating play is against Supercell's terms of service. I built this to
> study decision making. It is not affiliated with or endorsed by Supercell.

## How Jev decides

1. **Snapshot.** Every second the bot turns the newest frame into a state. The state holds your
   hand, your elixir, the next card, the troops on the board, tower health and the clock.
2. **Strategy.** Jev picks one strategy from a fixed list, and the bot always offers the whole list:
   `save_elixir`, `hold_elixir_for_threat`, `defend_left`, `defend_right`, `defend_centre`,
   `counter_push_left`,
   `counter_push_right`, `push_left`, `push_right`, `build_push`, `split_push`, `cycle`.
3. **Card.** Jev picks one of the four cards in your hand.
4. **Square.** Jev picks one of the squares the game allows for that card.

Each step depends on the one before it, so each step is its own request. A play costs three
requests. Choosing not to play costs one.

The bot asks Jev once per snapshot. The default is one snapshot a second, and `--every SECONDS`
changes it. When Jev picks `save_elixir` or `hold_elixir_for_threat`, the bot waits until your elixir
has gone up by one before it asks again. A new enemy troop, or damage to one of your towers, ends
the wait at once.

Over the 20 or so matches I have run, a match took 150 to 200 Jev requests and cost about $0.004.

### Design decisions

I wanted to measure Jev's decisions and not my own. These are the decisions I made about how to
ask, and why.

| Decision | Why |
| --- | --- |
| Every question carries its full option list: all 12 strategies, all 4 cards in hand, every square that is legal for the chosen card. The bot asks even when only one option exists. | A shortened list leads Jev toward an answer. I wanted to see whether its general reasoning carries over to a situation it has never seen, without me selecting the sensible options first. |
| The state holds measurements only. It has no `playable` flag, no list of counters and no previous decision. | A derived fact is me doing part of the reasoning. When the state listed the cards that counter a troop, the right card went from an even split to 98%. That number measured my list. |
| Option texts define and never judge. | A `not_for` that says "not when a tower is under attack" decides on Jev's behalf. A `not_for` that marks where one strategy becomes its neighbour keeps the options distinct and leaves the judgment to Jev. |
| Code acts only after Jev has chosen. | If code removed the cards Jev cannot afford, I could never see Jev choose to wait for one. When Jev picks a card it cannot afford, or a spell with nothing to cast it on, the bot taps nothing and the log records the pick. |
| Three questions in sequence, not one. | One question over every combination of strategy, card and square would hold hundreds of near-identical options. Three short lists keep the options distinct and show at which step a decision went wrong. |
| A fallback is never logged as Jev. | When a request fails the bot plays a baseline move. The log gives it its own source, so no analysis of Jev includes a move Jev did not make. |

Jev gets two kinds of knowledge with every question.

- A briefing on the game, from `clash_jev/game.py`. It covers the objective, elixir, the arena, a
  glossary, and what each card archetype is strong and weak against.
- A profile of every card in your hand and every troop the bot identified, from
  `clash_jev/cards.py`. A profile lists class, archetypes, health, damage and what the card can
  attack. The cards of the first two arenas also have a plain description with strengths and
  weaknesses. The code never says which of your cards answers which enemy troop. Jev works that out
  from the two profiles.

## Requirements

- macOS or Linux with Python 3.12 or newer.
- `adb`. On macOS, run `brew install android-platform-tools`.
- An Android phone or tablet with Clash Royale installed and USB debugging turned on. Emulators
  work on and off. The game's anti-tamper check closes it on some of them, and I do not try
  to get around that.
- A TypeSafe API key.

## Setup

```sh
git clone https://github.com/bytelabs-oss/clash-jev.git && cd clash-jev
python3.12 -m venv .venv
.venv/bin/pip install -e ".[dev]"
cp .env.example .env          # then put your TYPESAFE_API_KEY in it
```

Then connect the device.

1. On the device, open Settings, then About, and tap *Build number* seven times. Open Developer
   options and turn on *USB debugging*.
2. Plug the device in, accept the prompt on its screen, and check that `adb devices` lists it.
3. Open Clash Royale and enter a battle. The training camp is fine. Then run:

```sh
.venv/bin/clash-jev snap            # add --serial <id> if more than one device is attached
```

`snap` prints what it read and writes `snap.png`, a copy of the frame with every reading and tap
point drawn on it. It makes no Jev request. If it reports `NOT calibrated`, see
[Screen shapes](#screen-shapes).

## Playing

```sh
.venv/bin/clash-jev serve           # control page at http://127.0.0.1:8765
```

The page mirrors the device and shows what the bot is reading. Opening it asks Jev nothing.

Add `--arena N` with the arena you play in. Arena 0 is the training camp. Opponents in an arena only
own cards unlocked up to that arena, so the troop network only answers with those cards.

- **Start** tells the bot the battle has begun. From that press, the bot sends one snapshot a second
  to Jev and taps what Jev picks. Start the match yourself, then press Start.
- **Dry run** does the same but never taps.
- **Stop** ends the run. Nothing on the device's screen starts or stops a run.
- **Request cap** is a hard limit on Jev requests for the run. The default is 250, about one full
  match. Every run reports how many requests it made.

The page shows:

- Jev's choice for the decision it just made;
- the strategy, card and square steps of the last decision in which Jev picked a card, with the
  probability of every option;
- the full state the bot sent;
- the list of decisions so far, with runs of `save_elixir` folded into one line.

The bot appends every decision to `runs/<timestamp>.jsonl`. An entry holds the state, the questions,
the answers, the probabilities, the latency, and a small picture of the hand as the bot read it. The
bot also records a run started from the page as `runs/<timestamp>.mp4`, 480 pixels wide at 10 frames
a second. The video and the log share a clock, so second N of the video is second N of the log.

Other commands:

| Command | What it does |
| --- | --- |
| `clash-jev snap [--image file.png]` | Reads one frame, prints the state and the valid moves, and writes `snap.png`. It makes no Jev request. |
| `clash-jev play --web` | Plays without the control page's Start and Stop buttons. Ctrl+C ends it. It accepts `--dry-run`, `--every SECONDS`, `--max-requests N`, and `--policy baseline`, which plays without Jev. |
| `clash-jev play --image file.png` | Runs the whole pipeline once against a saved screenshot and makes exactly one decision. |
| `clash-jev add-card <card_id> --slot N` | Teaches the hand reader a card it does not recognise. See [Cards](#cards). |

The bot asks Jev at every snapshot while your hand is on screen, including when you can afford
nothing, because what to do with little elixir is Jev's decision. The bot does not resend a state
identical to the one Jev just answered. If a request fails, a simple baseline policy makes that one
decision.

## Replays, and asking Jev again

The replays at https://clash-jev.vercel.app come from recorded runs. This command turns a run into a
replay in `web/public/replays` and covers the opponent's name:

```sh
clash-jev publish runs/<run>-jev.jsonl
```

The bot serves published replays under the Replay tab of its own page. I deploy the public site
myself.

To ask Jev again, pause a replay on any decision and press *Re-ask Jev*. The request the bot sent
opens in three parts, which are the question with its options, the match state, and the game
briefing. You cannot change the state or the briefing, because the experiment is the same moment
with a different question. You can change the question. Edit its instructions, reword an option,
change a `not_for`, or add and remove options, either in a form or as raw JSON.

Paste your own TypeSafe API key and ask. The new probabilities appear next to the recorded ones. One
click makes one request on your key, and the page never makes a request on its own. The result shows
what Jev would choose at that moment. The recorded match does not change.

The TypeSafe API does not accept calls made straight from a web page, so the request goes through a
small forwarder. On the site it is `web/api/jev.js`, and on the bot it is `/api/jev`. The forwarder
passes on the one request with your key and stores neither.

## What the bot reads

| Field | How the bot reads it |
| --- | --- |
| Hand, 4 cards, each playable or not | `hand.py` matches the fine detail of each card's art against a bank of known cards. That detail survives the greying and the wipe the game draws over a card you cannot afford. A thumbnail of the whole shape is the fallback. A card is playable when it is in full colour from top to bottom. |
| Next card | The bot matches the "Next" thumbnail against the same bank. |
| Elixir, 0 to 10 | The bot counts the ten pips of the elixir bar. |
| Troops: owner, position, health | `units.py` finds level badges and the health bar attached to each. A crimson badge is the enemy's and a blue badge is yours. It reads them from a double-size drawing of the layout so that 10-pixel badges survive. |
| Troop identity, both sides | `troops.py` runs a small network I trained myself. It takes a picture of the spot under each badge and returns the card. I trained it on pictures from my own matches that I named by hand. It is 1.7 MB and runs through OpenCV. |
| Your own troops | The bot lists them like the enemy's, with lane, position, distance, health and time in view. The game only draws a badge on your troops once they are damaged, so the bot does not see an undamaged troop of yours. |
| Troops over time | `tracks.py` reads the troops about 4 times a second from the video, follows each troop from read to read, and lets every read vote on its name. It keeps a troop that is hidden for a moment, and the other reads outvote one bad frame. This costs no Jev requests. |
| Distance | For every troop, the bot counts the tiles to the tower it is walking toward. That is the other side's princess tower in its lane, or their king tower once the princess tower has fallen. |
| Lanes | The bot counts troops per lane and owner in three zones, which are your side, the bridge, and their side. |
| Princess towers | Health from 0 to 1 is the filled width of the tower's bar divided by the widest the bar has been. The bot marks a tower destroyed once its bar has been gone for 4 seconds, and keeps the last reading until then. It does not yet read the number printed beside the bar. |
| King towers | Health is 1.0 until a bar appears. After that it is the bar's width divided by the widest the bar has been. |
| Opponent elixir | The game never shows it, so `opponent.py` estimates it. The estimate starts at 5, refills on the match clock, and pays for each new enemy troop. |
| Clock | Seconds since Start, and whether elixir is single, double or triple. |

Technical limits:

- The troop network names 84% of troops correctly on play it was not trained on. It confuses Spear
  Goblins and Goblins more than any other pair, and it only knows the cards it has pictures of.
- The game draws a badge on your own troop only once it is damaged, so the bot does not see an
  undamaged troop of yours.
- Badges that touch in a crowd merge, so the bot misses some troops in a tight fight.
- Tower health is the filled width of a bar. In one recorded match a tower at 501 of 1750 read as
  0.97, because the reader counted the drained part of the bar as filled.
- A king tower that is already damaged when the bot first sees it reads as full.
- A frame is about 350 ms old when it is read, and three requests and a tap add roughly 560 ms.
- Enemy spells leave no troop, so the opponent elixir estimate runs high.
- The bot does not detect the start or the end of a match. The results screen gives meaningless
  readings, so press Stop when the match ends.

### Cards

`clash_jev/cards.py` has facts for 121 cards. Evolutions and heroes inherit from their base card.
Rarities and unlock arenas come from RoyaleAPI's public card data in `official_cards.json`.

The hand reader ships knowing the nine training-camp and arena-1 cards I built it on: archers,
arrows, fireball, giant, knight, mini pekka, minions, musketeer and spear goblins. On matches it had
not seen, it read 626 of 626 hand cards and 176 of 176 Next thumbnails correctly. Any other card
shows as `unknown` until you teach it. Do that once, with the card visible in your hand:

```sh
clash-jev add-card valkyrie --slot 3
```

This writes `clash_jev/extra_card_shapes.json`, which the bot loads on every start.

### Teaching it more troops

The network knows the cards listed in `clash_jev/troop_model.json`, which are the cards it has seen
pictures of. To teach it the cards of your arena:

```sh
clash-jev serve --collect troops/        # press Collect on the page and play a match yourself: no Jev requests
clash-jev label --collect troops/ --arena 2   # name each troop once, by key, in the browser
pip install -e ".[train]"                # PyTorch, only needed for this step
clash-jev train --collect troops/        # tests on play it has not seen, then writes clash_jev/troop_model.onnx
```

Collecting saves a small picture of every troop the bot sees, and a full frame every second. The bot
groups the pictures of one troop into a track, so you name a troop once and not once per picture. It
leaves out pictures in which the troop's badge is not where it should be. `train` prints, per card,
how many troops it named right on stretches of play it was not trained on.

### Squares

Troops go on your half. The squares there are the bridge, in front of a tower, the back, the centre
at the river, and the centre in front of your king tower. Buildings go on the defensive spots.
Pocket squares open when an enemy princess tower falls. The bot rebuilds a spell's squares from the
board on every snapshot, with one square for each standing enemy tower and one for each enemy troop
where it stands. A square's text says where the square is and never what to use it for.

## Screen shapes

The bot defines every reading on a 419x633 reference layout. The device keeps its native
resolution. `clash_jev/screenmap.py` maps the device's frame onto the reference with two affine
blocks, because Clash Royale scales the arena and the bottom bar separately. It also maps taps back
to real pixels.

Calibrations are keyed by aspect ratio. The repo includes 0.662, the reference shape, and 0.625,
which fits a 1440x2304 screen. For another shape, run `clash-jev snap`, compare the markers in
`snap.png` with the tower bars, elixir pips and hand cards, and add a `Calibration` entry.

## Development

```sh
.venv/bin/ruff check . && .venv/bin/python -m pytest -q
```

The tests run on saved frames with a fake `adb` and a fake Jev. They make no network requests.

| Module | Role |
| --- | --- |
| `pipeline.py` | The five functions at the top of this page. |
| `perception.py`, `hand.py`, `units.py`, `troops.py`, `tracks.py`, `opponent.py` | Turn a frame into a state. |
| `collect.py`, `label.py`, `train.py` | Teach the troop network by collecting pictures, naming them and training. |
| `screenmap.py` | Maps between the device's frame and the reference layout. |
| `moves.py` | Lists the legal squares for each card. |
| `game.py`, `cards.py`, `strategies.py` | Hold the knowledge and the options the bot gives Jev. |
| `policy.py` | Builds the state and the three questions. It contains `JevPolicy` and `BaselinePolicy`. |
| `runner.py`, `control.py`, `record.py` | Run the one-second loop, handle Start and Stop, and record the run's video. |
| `device.py` | Talks to adb. It takes an H.264 screen stream in and sends taps out. |
| `view.py`, `web/` | The bot's web server and the page it serves, which shows the live game and the replays in one Next.js and shadcn app. Build it with `cd web && npm install && npm run build`. |
| `publish.py` | Turns a recorded run into a replay. It covers the opponent's name and reads the score off the results screen. |

## Credits and licence

The code is released under the MIT licence. See `LICENSE`.

- All code, card shapes, the troop network and its weights, and the test frames in this repo are my
  own. I trained the troop network from scratch on pictures from my matches, which I named by hand.
- The layout of the battle screen, meaning where the hand, the elixir bar and the towers sit on a
  419x633 frame, is something I first worked out by studying
  [py-clash-bot](https://github.com/pyclashbot/py-clash-bot). I use none of its code, data or
  images.
- `clash_jev/official_cards.json` is from
  [RoyaleAPI's cr-api-data](https://github.com/RoyaleAPI/cr-api-data).
- Clash Royale, its cards and its artwork are trademarks and property of Supercell. This material is
  unofficial and Supercell does not endorse it. See
  [Supercell's Fan Content Policy](https://supercell.com/en/fan-content-policy/).
