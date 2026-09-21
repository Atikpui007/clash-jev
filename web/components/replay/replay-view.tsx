"use client"

import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { Crown, Layers, MessageSquare, Timer } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Select, SelectContent, SelectGroup, SelectItem, SelectLabel, SelectTrigger, SelectValue } from "@/components/ui/select"
import { cn } from "@/lib/utils"
import { clock, decisionAt, played, type Replay, stageAt, type Summary } from "@/lib/replay"
import { Dock } from "./dock"
import { Player } from "./player"
import { Reask } from "./reask"
import { type Mode, Shell } from "./shell"

/** "20260101-193000" -> "1 Jan · 19:30", in the reader's own locale. */
function when(id: string): string {
  const [, y, m, d, h, min] = id.match(/^(\d{4})(\d{2})(\d{2})-(\d{2})(\d{2})/) ?? []
  if (!y) return id
  const date = new Date(+y, +m - 1, +d, +h, +min)
  return `${date.toLocaleDateString(undefined, { day: "numeric", month: "short" })} · ${date.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" })}`
}

/** One match in a line: when it was played, and how it went in towers (destroyed, then lost). */
function MatchLine({ run }: { run: Summary }) {
  const ahead = run.towers_destroyed - run.towers_lost
  return (
    <span className="flex items-center gap-2">
      <span className="font-medium">{when(run.id)}</span>
      <Badge variant="outline" className={cn("gap-1 tabular-nums", ahead > 0 ? "border-ok/50 text-ok-fg" : ahead < 0 ? "border-bad/50 text-bad-fg" : "")}>
        <Crown className="size-3" /> {run.towers_destroyed}–{run.towers_lost}
      </Badge>
    </span>
  )
}

const fromLink = (name: string) => (typeof window === "undefined" ? null : new URLSearchParams(window.location.search).get(name))

/** The run picker. Each run is its own `Run`, keyed by id, so switching runs starts from a clean slate. */
export function ReplayView({ runs, onMode }: { runs: Summary[]; onMode: (mode: Mode) => void }) {
  // A link can open a run at a moment of the match: ?run=<id>&t=<seconds>
  const [id, setId] = useState(() => {
    const linked = fromLink("run")
    return runs.some((run) => run.id === linked) ? (linked as string) : runs[runs.length - 1].id
  })
  return <Run key={id} id={id} runs={runs} onPick={setId} onMode={onMode} />
}

function Run({ id, runs, onPick, onMode }: { id: string; runs: Summary[]; onPick: (id: string) => void; onMode: (mode: Mode) => void }) {
  const [replay, setReplay] = useState<Replay | null>(null)
  const [time, setTime] = useState(0)
  const [playing, setPlaying] = useState(false)
  const [speed, setSpeed] = useState(1)
  const [overlay, setOverlay] = useState(true)
  const video = useRef<HTMLVideoElement>(null)

  useEffect(() => {
    fetch(`/replays/${id}/replay.json`).then((r) => r.json()).then(setReplay)
  }, [id])

  // The video's own clock drives everything; it is read every animation frame so the pipeline can light up smoothly.
  useEffect(() => {
    let frame = 0
    const tick = () => {
      const element = video.current
      if (element) {
        setTime(element.currentTime)
        setPlaying(!element.paused && !element.ended)
      }
      frame = requestAnimationFrame(tick)
    }
    frame = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(frame)
  }, [])

  useEffect(() => {
    const at = Number(fromLink("t"))
    const element = video.current
    if (!replay || !element || !at) return
    const go = () => void (element.currentTime = at)
    if (element.readyState >= 1) go()
    else element.addEventListener("loadedmetadata", go, { once: true })
  }, [replay])

  const decisions = useMemo(() => replay?.decisions ?? [], [replay])
  const duration = replay?.summary.seconds ?? 0
  const index = decisionAt(decisions, time)
  const decision = index >= 0 ? decisions[index] : null
  // The steps shown are those of the last decision in which Jev picked a card, so "save elixir" does not wipe them.
  const picked = useMemo(() => {
    for (let i = index; i >= 0; i--) if (decisions[i].card_choice) return decisions[i]
    return null
  }, [decisions, index])
  // The walk through the pipeline has until the next decision starts.
  const next = decisions[index + 1]?.state_elapsed ?? duration
  const active = decision ? stageAt(decision, (time - decision.state_elapsed) * 1000, (next - decision.state_elapsed) * 1000) : null

  const seek = useCallback((to: number) => {
    if (video.current) video.current.currentTime = to
  }, [])
  const toggle = useCallback(() => {
    const element = video.current
    if (element) void (element.paused ? element.play() : element.pause())
  }, [])
  const toPlay = useCallback(
    (direction: -1 | 1) => {
      const times = decisions.filter(played).map((d) => d.state_elapsed)
      const next = direction === 1 ? times.find((t) => t > time + 0.2) : [...times].reverse().find((t) => t < time - 1.5)
      if (next !== undefined) seek(Math.max(0, next - 0.3))
    },
    [decisions, time, seek],
  )
  useEffect(() => {
    if (video.current) video.current.playbackRate = speed
  }, [speed, replay])
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === " ") {
        e.preventDefault()
        toggle()
      }
      if (e.key === "ArrowRight") toPlay(1)
      if (e.key === "ArrowLeft") toPlay(-1)
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [toggle, toPlay])

  const summary = replay?.summary
  const headerRight = (
    <>
      {summary && (
        <div className="flex items-center gap-1.5 max-lg:order-last max-lg:w-full max-lg:flex-wrap">
          <Badge variant="outline" className="gap-1"><Crown className="size-3" /> {summary.towers_destroyed} destroyed · {summary.towers_lost} lost</Badge>
          <Badge variant="outline" className="gap-1"><Layers className="size-3" /> {summary.plays} cards played</Badge>
          <Badge variant="outline" className="gap-1"><MessageSquare className="size-3" /> {summary.requests} Jev requests</Badge>
          <Badge variant="outline" className="mr-2 gap-1"><Timer className="size-3" /> {summary.decisions} decisions</Badge>
        </div>
      )}
      <Select value={id} onValueChange={(value) => value && onPick(value as string)}>
        <SelectTrigger className="h-10 min-w-0 gap-2 max-lg:flex-1 lg:min-w-64" aria-label="Choose a match">
          <SelectValue>
            {(value) => {
              const run = runs.find((candidate) => candidate.id === value)
              return run ? <MatchLine run={run} /> : "Choose a match"
            }}
          </SelectValue>
        </SelectTrigger>
        {/* Opens under the button. Opened over it, releasing the click would pick the match under the pointer. */}
        <SelectContent side="bottom" align="end" sideOffset={6} alignItemWithTrigger={false} className="min-w-[min(20rem,calc(100vw-1.5rem))]">
          <SelectGroup>
            <SelectLabel>Recorded matches · newest first</SelectLabel>
            {runs
              .slice()
              .reverse()
              .map((run) => (
                <SelectItem key={run.id} value={run.id} className="py-2">
                  <span className="flex flex-col gap-0.5">
                    <MatchLine run={run} />
                    <span className="text-xs text-muted-foreground tabular-nums">
                      {clock(run.seconds)} long · {run.plays} cards played · {run.requests} Jev requests
                    </span>
                  </span>
                </SelectItem>
              ))}
          </SelectGroup>
        </SelectContent>
      </Select>
    </>
  )
  const screen = summary?.has_video ? (
    <Player videoRef={video} src={`/replays/${id}/video.mp4`} decisions={decisions} current={decision} time={time} duration={duration} overlay={overlay} onSeek={seek} />
  ) : (
    <div className="grid aspect-[5/8] w-full place-items-center rounded-xl border text-sm text-muted-foreground">{replay ? "This run has no video." : "Loading…"}</div>
  )
  return (
    <Shell
      mode="replay"
      onMode={onMode}
      headerRight={headerRight}
      screen={screen}
      dock={<Dock playing={playing} time={time} duration={duration} speed={speed} overlay={overlay} onToggle={toggle} onPlay={toPlay} onSpeed={setSpeed} onOverlay={() => setOverlay(!overlay)} />}
      decision={decision}
      picked={picked}
      active={active}
      questions={replay?.questions ?? {}}
      state={decision?.state ?? null}
      briefing={replay?.briefing ?? null}
      decisions={decisions}
      current={index}
      onSeek={seek}
      reask={decision && decision.source === "jev" && decision.strategy_probabilities ? <Reask key={`${id}-${decision.state_elapsed}`} decision={decision} briefing={replay?.briefing ?? null} questions={replay?.questions ?? {}} onOpen={() => video.current?.pause()} /> : null}
    />
  )
}
