"use client"

// Live mode: the same panels as a replay, fed by the bot running on this machine instead of by a recording.

import { useEffect, useRef, useState } from "react"
import type { Decision, SentState, Step } from "./replay"

// The bot serves this app itself (then its data is next door, same origin); while developing the app on another
// port, the bot is looked for at its usual address.
const servedByBot = typeof window !== "undefined" && window.location.port === "8765"
export const BOT = process.env.NEXT_PUBLIC_BOT_URL ?? (servedByBot ? "" : "http://127.0.0.1:8765")

export type Control = {
  running: boolean
  mode: string
  cap: number | null
  message: string
  events: string[]
  requests?: number
  decisions?: number
  cards_played?: number
}

type Logged = Omit<Decision, "state" | "options" | "units"> & {
  request?: { state: SentState & { game?: Record<string, unknown> }; questions: Partial<Record<Step, { instructions: string; options: Record<string, unknown> }>> }
  state?: { units?: Decision["units"] }
}

type Latest = {
  state?: SentState & { game?: Record<string, unknown> }
  history: Logged[]
  last_play: Logged | null
  units?: Decision["units"]
  control: Control | null
  boot?: number
}

/** A log entry as the bot publishes it -> the shape the panels read. */
function asDecision(entry: Logged, fallback: SentState): Decision {
  const questions = entry.request?.questions ?? {}
  return {
    ...entry,
    state: entry.request?.state ?? fallback,
    options: Object.fromEntries(Object.entries(questions).map(([step, question]) => [step, question?.options ?? {}])),
    units: entry.state?.units ?? [],
  }
}

export type Live = {
  connected: boolean
  state: SentState | null
  briefing: Record<string, unknown> | null
  decisions: Decision[] // oldest first
  picked: Decision | null
  questions: Partial<Record<Step, string>>
  units: Decision["units"]
  control: Control | null
  boot: number
  arrivedAt: number // when the newest decision reached the page, to light the pipeline from
}

export function useLive(enabled: boolean): Live {
  const [latest, setLatest] = useState<Latest | null>(null)
  const [connected, setConnected] = useState(false)
  const [arrivedAt, setArrivedAt] = useState(0)
  const newest = useRef<number | null>(null)

  useEffect(() => {
    if (!enabled) return
    let stopped = false
    const poll = async () => {
      try {
        const answer: Partial<Latest> = await fetch(`${BOT}/latest.json`, { cache: "no-store" }).then((r) => r.json())
        if (stopped) return
        // Before the bot has read a first frame (no device yet) it answers with its status and nothing else.
        const data: Latest = { history: [], last_play: null, control: null, ...answer }
        const top = data.history[0]?.state_elapsed ?? null
        if (top !== newest.current) {
          newest.current = top
          setArrivedAt(performance.now())
        }
        setLatest(data)
        setConnected(true)
      } catch {
        if (!stopped) setConnected(false)
      }
    }
    void poll()
    const timer = setInterval(poll, 400)
    return () => {
      stopped = true
      clearInterval(timer)
    }
  }, [enabled])

  const state = latest?.state?.hand ? latest.state : null
  const blank = state ?? ({} as SentState)
  const questions: Partial<Record<Step, string>> = {}
  for (const entry of [latest?.last_play, latest?.history[0]])
    for (const [step, question] of Object.entries(entry?.request?.questions ?? {})) questions[step as Step] ??= question?.instructions
  // The live page shows the run that is on. The bot keeps the last run's decisions after it ends. Those are not
  // shown here: a finished run is watched under Replay.
  const running = latest?.control?.running ?? false
  return {
    connected,
    state,
    briefing: latest?.state?.game ?? null,
    decisions: running ? [...(latest?.history ?? [])].reverse().map((entry) => asDecision(entry, blank)) : [],
    picked: running && latest?.last_play ? asDecision(latest.last_play, blank) : null,
    questions,
    units: latest?.units ?? [],
    control: latest?.control ?? null,
    boot: latest?.boot ?? 0,
    arrivedAt,
  }
}

export async function command(path: "/start" | "/stop", body: Record<string, unknown> = {}) {
  // Sent as plain text so the browser needs no permission round-trip first; the bot parses the JSON itself.
  await fetch(`${BOT}${path}`, { method: "POST", body: JSON.stringify(body) }).catch(() => undefined)
}
