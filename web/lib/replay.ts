// The shape of a published replay (written by `clash-jev publish`) and the small helpers every panel shares.

export type Odds = Record<string, number>

export type Troop = {
  troop: string
  type?: string
  class?: string
  archetypes?: string[]
  lane: string
  where: string
  tiles_from_my_tower?: number
  tiles_from_enemy_tower?: number
  that_tower?: string
  seen_for_seconds?: number | null
  health_remaining: number
}

export type HandCard = {
  card: string
  type?: string
  elixir_cost: number | null
  elixir_left_after_playing: number | null
  class?: string
  archetypes?: string[]
  description?: string
  strengths?: string[]
  weaknesses?: string[]
}

export type SentState = {
  clock: { elapsed_seconds: number; elixir_rate: string; seconds_between_snapshots?: number }
  elixir: number
  elixir_leak?: { leaking_now: boolean; seconds_at_10: number }
  hand: HandCard[]
  next_card: string
  enemy_elixir_estimate: number | null
  my_troops?: Troop[]
  enemy_troops: Troop[]
  towers: Record<string, number | string>
}

export type Decision = {
  state_elapsed: number
  action: string
  note?: string
  source: string
  latency_ms?: number
  step_ms?: Partial<Record<Step, number>>
  requests_made?: number
  square_xy?: [number, number] | null
  strategy_choice?: string
  strategy_probabilities?: Odds
  card_choice?: string
  card_probabilities?: Odds
  square_choice?: string
  square_probabilities?: Odds
  state: SentState
  options: Partial<Record<Step, Record<string, unknown>>>
  units: { owner: string; x: number; y: number; name: string | null; health: number | null }[]
}

export type Summary = {
  id: string
  title: string
  seconds: number
  decisions: number
  plays: number
  requests: number
  towers_destroyed: number
  towers_lost: number
  has_video: boolean
}

export type Replay = {
  summary: Summary
  briefing: Record<string, unknown> | null
  questions: Partial<Record<Step, string>>
  decisions: Decision[]
}

export type Step = "strategy" | "card" | "square"
export const STEPS: Step[] = ["strategy", "card", "square"]

export const nice = (name: string | null | undefined) =>
  (name ?? "")
    .replace(/^play_/, "")
    .replace(/_slot\d$/, "")
    .replace(/^enemy_(.*)_(left|right)_\d+$/, "on the enemy $1")
    .replaceAll("_", " ")

export const played = (d: Decision) => d.action.includes(" -> ")

export const clock = (seconds: number) =>
  `${Math.floor(seconds / 60)}:${String(Math.floor(seconds % 60)).padStart(2, "0")}`

/** The decision in force at `time`: the last one made at or before it. */
export function decisionAt(decisions: Decision[], time: number): number {
  let low = 0
  let high = decisions.length - 1
  let found = -1
  while (low <= high) {
    const middle = (low + high) >> 1
    if (decisions[middle].state_elapsed <= time) {
      found = middle
      low = middle + 1
    } else high = middle - 1
  }
  return found
}

// The stages a snapshot passes through. The first three happen on the machine in a few milliseconds; the three
// steps are requests to Jev, each taking as long as the log says it took; a tap follows only when a card is played.
export const STAGES = ["capture", "vision", "state", "strategy", "card", "square", "tap"] as const
export type Stage = (typeof STAGES)[number]
const LOCAL_MS = 50

export function stageTimes(d: Decision): { stage: Stage; from: number; to: number; ran: boolean }[] {
  const asked = STEPS.filter((step) => d[`${step}_probabilities` as const])
  const each = d.latency_ms && asked.length ? d.latency_ms / asked.length : 150
  let at = 0
  return STAGES.map((stage) => {
    const isStep = (STEPS as readonly string[]).includes(stage)
    const ran = isStep ? asked.includes(stage as Step) : stage === "tap" ? played(d) : true
    const took = !ran ? 0 : isStep ? (d.step_ms?.[stage as Step] ?? each) : stage === "tap" ? 140 : LOCAL_MS
    const times = { stage, from: at, to: at + took, ran }
    at += took
    return times
  })
}

/**
 * Which stage is lit `sinceMs` after the decision began. A decision takes a few hundred milliseconds, too fast to
 * follow, so it is slowed down, but only as far as fits in `roomMs`, the time before the next decision starts, so
 * the walk always reaches its end. Once there it stays on the last stage that ran: Tap for a card played, Step 2
 * when code declined the card, Step 1 when the strategy was to play nothing.
 */
export function stageAt(d: Decision, sinceMs: number, roomMs = 1000): Stage | null {
  const times = stageTimes(d).filter((t) => t.ran)
  if (!times.length || sinceMs < 0) return null
  const total = times[times.length - 1].to
  const stretch = Math.max(1, Math.min(4, (roomMs * 0.7) / total))
  const hit = times.find((t) => sinceMs >= t.from * stretch && sinceMs < t.to * stretch)
  return (hit ?? times[times.length - 1]).stage
}
