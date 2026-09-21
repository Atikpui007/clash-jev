# clash-jev web app

The page the bot serves: the **live game** and the **replays**, in one Next.js + shadcn/ui app.

```sh
npm install
npm run build        # writes out/, which `clash-jev serve` serves at http://127.0.0.1:8765
npm run dev          # while working on the app: http://localhost:3000, talking to the bot on :8765
```

- `components/replay/shell.tsx` is the one screen both modes share: the pipeline strip, then the match, what Jev
  did and what Jev knew, side by side, filling the window.
- `lib/live.ts` reads the running bot (`/latest.json`, `/stream.mjpg`, `POST /start`, `POST /stop`).
- `lib/replay.ts` is the shape of a published replay. `clash-jev publish runs/<run>-jev.jsonl` writes one into
  `public/replays/`, with the players' names covered and the results screen cut off.
- A link can open a moment of a match: `?mode=replay&run=<id>&t=<seconds>`.
