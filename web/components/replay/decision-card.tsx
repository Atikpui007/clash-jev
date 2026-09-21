"use client"

import type { ReactNode } from "react"
import { Ban, Hourglass, Info, Swords, Zap } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip"
import { cn } from "@/lib/utils"
import { clock, type Decision, nice, played, type Step, STEPS } from "@/lib/replay"
import { Disclosure } from "./disclosure"
import { OddsBars } from "./odds"

const STEP_TITLE = { strategy: "Step 1 · which strategy", card: "Step 2 · which card", square: "Step 3 · where" } as const

const percent = (odds?: Record<string, number>, choice?: string) => (odds && choice && odds[choice] !== undefined ? Math.round(odds[choice] * 100) : null)

/** How sure Jev was of one step: green when it was clear, amber when it was close to a coin flip. */
function Sure({ step, value }: { step: string; value: number | null }) {
  if (value === null) return null
  return (
    <Badge variant="outline" className={cn("gap-1 px-2.5 py-1 text-sm", value >= 70 ? "border-ok/50 text-ok-fg" : value < 40 ? "border-warn/50 text-warn-fg" : "")}>
      {step} <span className="font-semibold tabular-nums">{value}%</span>
    </Badge>
  )
}

/** What Jev just decided: the headline of the page, with the facts behind it as chips. */
export function DecisionCard({ decision, idle, reask }: { decision: Decision | null; idle?: string; reask?: ReactNode }) {
  if (!decision)
    return (
      <Card className="shrink-0">
        <CardContent className="py-8 text-center text-sm text-muted-foreground">{idle ?? "Jev's first decision comes with the first snapshot."}</CardContent>
      </Card>
    )
  const didPlay = played(decision)
  const [card, square] = didPlay ? decision.action.split(" -> ") : []
  const waiting = !didPlay && !decision.card_choice
  const Icon = didPlay ? Swords : waiting ? Hourglass : Ban
  return (
    <Card className={cn("shrink-0 gap-2 overflow-hidden py-4", didPlay && "border-jev/50")}>
      <CardHeader className="px-5">
        <div className="flex items-center justify-between gap-2">
          <CardTitle className="text-sm font-medium uppercase tracking-wider text-muted-foreground">Jev&apos;s choice</CardTitle>
          <div className="flex items-center gap-1.5 text-sm text-muted-foreground">
            <span className="tabular-nums">{clock(decision.state_elapsed)}</span>
            <span>·</span>
            <Zap className="size-3" />
            <span className="tabular-nums">{decision.latency_ms ?? "–"} ms</span>
            <span>·</span>
            <span>{decision.requests_made ?? 0} request{decision.requests_made === 1 ? "" : "s"}</span>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-3 px-5">
        <div className="flex items-start gap-3">
          <div className={cn("grid size-14 shrink-0 place-items-center rounded-xl", didPlay ? "bg-jev/20 text-jev-fg" : "bg-muted text-muted-foreground")}>
            <Icon className="size-7" />
          </div>
          <div className="min-w-0">
            <div className="text-2xl font-semibold leading-tight tracking-tight capitalize 2xl:text-3xl">
              {didPlay ? (
                <>
                  {nice(card)} <span className="text-muted-foreground">→</span> {nice(square)}
                </>
              ) : waiting ? (
                nice(decision.strategy_choice)
              ) : (
                <>
                  {nice(decision.card_choice)} <span className="text-base font-normal normal-case text-muted-foreground">— not played</span>
                </>
              )}
            </div>
            {decision.note && <p className="mt-1 text-sm text-warn-fg">{decision.note}</p>}
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          <Badge variant="secondary" className="px-2.5 py-1 text-sm capitalize">{nice(decision.strategy_choice) || "no strategy"}</Badge>
          <Sure step="strategy" value={percent(decision.strategy_probabilities, decision.strategy_choice)} />
          <Sure step="card" value={percent(decision.card_probabilities, decision.card_choice)} />
          <Sure step="square" value={percent(decision.square_probabilities, decision.square_choice)} />
          {decision.source !== "jev" && <Badge variant="destructive" className="px-2.5 py-1 text-sm">fallback, not Jev</Badge>}
          {reask && <span className="ml-auto">{reask}</span>}
        </div>
      </CardContent>
    </Card>
  )
}

/** The three questions of one decision, each with the odds Jev gave every option. */
function Asked({ step, question, options, chosen }: { step: Step; question?: string; options?: Record<string, unknown>; chosen?: string }) {
  if (!question && !options) return null
  // What went over the wire for this step, next to the state: the question and every option, exactly as worded.
  const raw = { [step]: { instructions: question ?? "", options: options ?? {} } }
  return (
    <Disclosure label="Question and options">
      <Tabs defaultValue="readable" className="gap-2">
        <TabsList>
          <TabsTrigger value="readable">Readable</TabsTrigger>
          <TabsTrigger value="json">Raw JSON</TabsTrigger>
        </TabsList>
        <TabsContent value="readable">
          <div className="space-y-3 rounded-lg border bg-muted/30 p-3">
            {question && <p className="whitespace-pre-wrap text-sm leading-relaxed text-muted-foreground">{question}</p>}
            <ul className="space-y-2">
              {Object.entries(options ?? {}).map(([name, text]) => {
                const worded = typeof text === "string" ? { what: text } : (text as { what?: string; not_for?: string })
                return (
                  <li key={name} className={cn("rounded-md border px-3 py-2 text-sm", name === chosen && "border-jev/50 bg-jev/10")}>
                    <div className="font-medium capitalize">{nice(name)}</div>
                    {worded.what && <div className="text-muted-foreground">{worded.what}</div>}
                    {worded.not_for && (
                      <div className="mt-1 text-warn-fg">
                        <span className="font-medium">Not for:</span> {worded.not_for}
                      </div>
                    )}
                  </li>
                )
              })}
            </ul>
          </div>
        </TabsContent>
        <TabsContent value="json">
          <pre className="max-h-96 overflow-auto whitespace-pre-wrap rounded-lg border bg-muted/30 p-3 font-mono text-xs leading-relaxed">{JSON.stringify(raw, null, 2)}</pre>
        </TabsContent>
      </Tabs>
    </Disclosure>
  )
}

export function StepsCard({ decision, current, questions }: { decision: Decision | null; current: boolean; questions: Partial<Record<Step, string>> }) {
  if (!decision) return null
  const [card, square] = played(decision) ? decision.action.split(" -> ") : []
  return (
    <Card className="flex min-h-0 flex-1 flex-col gap-3 py-4 max-lg:max-h-[32rem] max-lg:flex-none">
      <CardHeader className="shrink-0 px-5">
        <div className="flex items-center justify-between gap-3">
          <CardTitle className="flex items-center gap-2 text-sm font-medium uppercase tracking-wider text-muted-foreground">
            Last card played
            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger className="text-muted-foreground hover:text-foreground">
                  <Info className="size-4" />
                </TooltipTrigger>
                <TooltipContent>Shows Jev&apos;s last move that was not save elixir, so its three steps stay visible while it waits.</TooltipContent>
              </Tooltip>
            </TooltipProvider>
          </CardTitle>
          <span className="shrink-0 text-sm text-muted-foreground">{current ? "this decision" : `at ${clock(decision.state_elapsed)}`}</span>
        </div>
        {/* When the last card played IS the decision above, its name is already up there. */}
        <div className={cn("text-lg font-semibold capitalize leading-tight", current && "hidden")}>
          {card ? (
            <>
              {nice(card)} <span className="text-muted-foreground">→</span> {nice(square)}
            </>
          ) : (
            <>
              {nice(decision.card_choice)} <span className="text-sm font-normal normal-case text-warn-fg/90">— picked, but could not be played</span>
            </>
          )}
        </div>
      </CardHeader>
      <CardContent className="min-h-0 flex-1 space-y-4 overflow-y-auto px-5">
        {STEPS.map((step) => {
          const odds = decision[`${step}_probabilities` as const]
          const chosen = decision[`${step}_choice` as const]
          return (
            <div key={step} className="space-y-2">
              <div className="flex items-baseline justify-between gap-2">
                <span className="text-sm font-medium">{STEP_TITLE[step]}</span>
                {odds && chosen && <span className="truncate text-sm capitalize text-jev-fg">{nice(chosen)}</span>}
              </div>
              {odds ? (
                <>
                  <OddsBars odds={odds} chosen={chosen} />
                  <Asked step={step} question={questions[step]} options={decision.options[step]} chosen={chosen} />
                </>
              ) : (
                <p className="text-sm text-muted-foreground">
                  {step === "square" && decision.note ? "That card could not be played, so no square was asked." : "Not asked: the strategy plays nothing."}
                </p>
              )}
            </div>
          )
        })}
      </CardContent>
    </Card>
  )
}
