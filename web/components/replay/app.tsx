"use client"

import { useEffect, useState } from "react"
import { LiveView } from "@/components/replay/live-view"
import { ReplayView } from "@/components/replay/replay-view"
import type { Mode } from "@/components/replay/shell"
import { Shell } from "@/components/replay/shell"
import type { Summary } from "@/lib/replay"

/** The home page is the live game on the machine that runs the bot, and the replays anywhere else. A link can override that. */
function linkedMode(): Mode {
  const asked = new URLSearchParams(window.location.search).get("mode")
  if (asked === "live" || asked === "replay") return asked
  if (new URLSearchParams(window.location.search).has("t") || new URLSearchParams(window.location.search).has("run")) return "replay"
  return ["localhost", "127.0.0.1"].includes(window.location.hostname) ? "live" : "replay"
}

export default function App() {
  const [mode, setMode] = useState<Mode>(linkedMode)
  const [runs, setRuns] = useState<Summary[] | null>(null)
  useEffect(() => {
    fetch("/replays/index.json")
      .then((r) => (r.ok ? r.json() : []))
      .then(setRuns)
      .catch(() => setRuns([]))
  }, [])
  if (mode === "live") return <LiveView onMode={setMode} />
  if (runs?.length) return <ReplayView runs={runs} onMode={setMode} />
  return (
    <Shell
      mode="replay"
      onMode={setMode}
      headerRight={null}
      dock={null}
      screen={
        <div className="grid aspect-[5/8] w-full place-items-center rounded-xl border p-6 text-center text-sm text-muted-foreground">
          {runs ? "No replay has been published yet. Record a match, then run: clash-jev publish runs/<run>-jev.jsonl" : "Loading…"}
        </div>
      }
      decision={null}
      picked={null}
      active={null}
      questions={{}}
      state={null}
      briefing={null}
      decisions={[]}
      current={-1}
    />
  )
}
