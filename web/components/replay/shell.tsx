"use client"

import type { CSSProperties, ReactNode } from "react"
import { Radio, Rewind } from "lucide-react"
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"
import type { Decision, SentState, Stage, Step } from "@/lib/replay"
import { DecisionCard, StepsCard } from "./decision-card"
import { Pipeline } from "./pipeline"
import { StateCard } from "./state-card"
import { ThemeToggle } from "./theme-toggle"
import { Timeline } from "./timeline"

export type Mode = "live" | "replay"

/** The one screen both modes share: header, pipeline, then the match, what Jev did and what Jev knew, side by side. */
export function Shell({
  mode,
  onMode,
  headerRight,
  screen,
  dock,
  decision,
  picked,
  active,
  questions,
  state,
  briefing,
  decisions,
  current,
  onSeek,
  idle,
  noState,
  reask,
}: {
  mode: Mode
  onMode: (mode: Mode) => void
  headerRight: ReactNode
  screen: ReactNode
  dock: ReactNode
  decision: Decision | null
  picked: Decision | null
  active: Stage | null
  questions: Partial<Record<Step, string>>
  state: SentState | null
  briefing: Record<string, unknown> | null
  decisions: Decision[]
  current: number
  onSeek?: (time: number) => void
  idle?: string
  noState?: string
  reask?: ReactNode
}) {
  return (
    <main className="flex flex-col gap-2.5 p-3 max-lg:min-h-dvh max-lg:pb-24 lg:h-dvh lg:min-h-[640px] lg:overflow-hidden">
      <header className="flex shrink-0 flex-wrap items-center justify-between gap-x-6 gap-y-2 lg:h-11 lg:flex-nowrap">
        <div className="flex min-w-0 items-center gap-3 max-lg:w-full max-lg:justify-between lg:gap-5">
          <h1 className="text-xl font-semibold lg:text-2xl leading-none tracking-tight">clash-jev</h1>
          <Tabs value={mode} onValueChange={(value) => onMode(value as Mode)}>
            <TabsList className="h-10 p-1">
              <TabsTrigger value="live" className="gap-2 px-3 text-sm lg:px-5 lg:text-base">
                <Radio className="size-4" /> Live game
              </TabsTrigger>
              <TabsTrigger value="replay" className="gap-2 px-3 text-sm lg:px-5 lg:text-base">
                <Rewind className="size-4" /> Replay
              </TabsTrigger>
            </TabsList>
          </Tabs>
        </div>
        <div className="flex min-w-0 items-center justify-end gap-1.5 max-lg:w-full max-lg:flex-wrap lg:overflow-hidden">
          {headerRight}
          <ThemeToggle />
        </div>
      </header>

      <div className="max-lg:hidden">
        <Pipeline decision={decision} active={active} every={state?.clock?.seconds_between_snapshots} />
      </div>

      {/* Three columns share the rest of the window. The screen is 5:8, so its column is as wide as the height left
          under the header and the pipeline allows. Nothing scrolls the page; a crowded card scrolls inside itself.
          On a phone it is one column that scrolls, with the match pinned to the top so it stays in view. */}
      <div
        className="grid gap-4 max-lg:grid-cols-1 lg:min-h-0 lg:flex-1 lg:[grid-template-columns:var(--columns)]"
        style={{ "--columns": `min(48vw, calc((100dvh - ${mode === "live" ? 8.25 : 11.25}rem) * 0.625)) minmax(0, 1fr) minmax(0, 1fr)` } as CSSProperties}
      >
        <section aria-label="The match" className="min-h-0 max-lg:sticky max-lg:top-0 max-lg:z-20 max-lg:-mx-3 max-lg:bg-background max-lg:px-3 max-lg:pb-1">
          {screen}
        </section>
        {/* On a phone the pipeline sits under the match, so the screen comes first and can be larger. */}
        <div className="lg:hidden">
          <Pipeline decision={decision} active={active} every={state?.clock?.seconds_between_snapshots} />
        </div>
        <section aria-label="What Jev did" className="flex min-h-0 flex-col gap-4">
          <DecisionCard decision={decision} idle={idle} reask={reask} />
          <StepsCard decision={picked} current={picked !== null && picked.state_elapsed === decision?.state_elapsed} questions={questions} />
        </section>
        <aside aria-label="What Jev knew" className="flex min-h-0 flex-col gap-4">
          <StateCard state={state} briefing={briefing} empty={noState} />
          <Timeline decisions={decisions} current={current} onSeek={onSeek} />
        </aside>
      </div>
      {dock}
    </main>
  )
}
