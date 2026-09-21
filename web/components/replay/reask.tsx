"use client"

import { useMemo, useState } from "react"
import { FlaskConical, KeyRound, Loader2, Lock, RotateCcw } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Textarea } from "@/components/ui/textarea"
import { cn } from "@/lib/utils"
import { type Decision, nice, type Odds, type Step, STEPS } from "@/lib/replay"
import { Meter } from "./meter"
import { QuestionForm } from "./request-form"

const STEP_TITLE: Record<Step, string> = { strategy: "1 · Strategy", card: "2 · Card", square: "3 · Square" }

type Part = "question" | "state" | "game"
const PARTS: Part[] = ["question", "state", "game"]
const PART_TITLE: Record<Part, string> = { question: "Question", state: "State", game: "Briefing" }
const LOCKED: Record<Exclude<Part, "question">, string> = {
  state: "The match at this moment, as the bot read it. Recorded, so it cannot be changed here.",
  game: "The briefing every request carries: the game, its rules and its terms. Recorded, so it cannot be changed here.",
}

type Wording = { what?: string; not_for?: string } | string
type Asked = { state: Record<string, unknown>; questions: Record<string, { type: "choice"; instructions: string; criteria: Record<string, Wording> }> }
type Result = { choice: string; odds: Odds; ms: number }

/** Exactly what was sent for one step of a recorded decision: the state (with the briefing every request carries,
 *  and the earlier steps' picks as context) and the one question with every option as it was worded. */
function recorded(decision: Decision, step: Step, briefing: Record<string, unknown> | null, questions: Partial<Record<Step, string>>): Asked {
  let state: Record<string, unknown> = { ...(briefing ? { game: briefing } : {}), ...decision.state }
  const strategy = decision.strategy_choice
  if (step !== "strategy" && strategy) {
    const worded = decision.options.strategy?.[strategy] as Wording | undefined
    state = { strategy: { name: strategy, meaning: typeof worded === "string" ? worded : worded?.what }, ...state }
  }
  if (step === "square" && decision.card_choice) {
    const name = decision.card_choice.replace(/^play_/, "").replace(/_slot\d$/, "")
    const held = decision.state.hand?.find((card) => card.card === name) as Record<string, unknown> | undefined
    const facts = Object.fromEntries(Object.entries(held ?? { card: name }).filter(([fact]) => fact !== "elixir_left_after_playing"))
    state = { playing: facts, ...state }
  }
  return { state, questions: { [step]: { type: "choice", instructions: questions[step] ?? "", criteria: (decision.options[step] ?? {}) as Record<string, Wording> } } }
}

function Compare({ before, after }: { before?: Odds; after: Result }) {
  const names = [...new Set([...Object.keys(after.odds), ...Object.keys(before ?? {})])].sort((a, b) => (after.odds[b] ?? 0) - (after.odds[a] ?? 0))
  return (
    <ul className="space-y-1.5">
      {names.map((name) => {
        const now = after.odds[name] ?? 0
        const was = before?.[name]
        const change = was === undefined ? null : Math.round((now - was) * 100)
        return (
          <li key={name} className="grid grid-cols-[minmax(0,11rem)_1fr_3rem_3.5rem] items-center gap-2 text-sm">
            <span className={cn("truncate", name === after.choice ? "font-semibold" : "text-muted-foreground")}>{nice(name)}</span>
            <Meter value={Math.max(0.015, now)} tone={name === after.choice ? "violet" : "quiet"} thick />
            <span className="text-right tabular-nums">{Math.round(now * 100)}%</span>
            <span className={cn("text-right text-xs tabular-nums", !change ? "text-muted-foreground" : change > 0 ? "text-ok-fg" : "text-bad-fg")}>
              {change === null ? "new" : change === 0 ? "±0" : `${change > 0 ? "+" : ""}${change}`}
            </span>
          </li>
        )
      })}
    </ul>
  )
}

/** Pause on a decision, change anything that was sent to Jev (a fact of the state, a question, an option, a not_for)
 *  and ask again with your own TypeSafe key. One click is one request; nothing is asked on its own. */
export function Reask({ decision, briefing, questions, onOpen }: { decision: Decision; briefing: Record<string, unknown> | null; questions: Partial<Record<Step, string>>; onOpen?: () => void }) {
  const steps = STEPS.filter((step) => decision[`${step}_probabilities` as const])
  const [step, setStep] = useState<Step>("strategy")
  const [part, setPart] = useState<Part>("question")
  const [asJson, setAsJson] = useState(false) // the form by default, the raw JSON on request
  const [drafts, setDrafts] = useState<Record<string, string | undefined>>({})
  const [results, setResults] = useState<Partial<Record<Step, Result>>>({})
  const [key, setKey] = useState("") // lives in this panel only: never stored, gone when the page is closed
  const [busy, setBusy] = useState(false)
  const [problem, setProblem] = useState<string | null>(null)
  // The request in three parts, so the long briefing does not bury the match state and the question.
  const originals = useMemo(() => {
    const { state, questions: asked } = recorded(decision, step, briefing, questions)
    const { game, ...match } = state
    const pretty = (value: unknown) => JSON.stringify(value ?? {}, null, 2)
    return { question: pretty(asked), state: pretty(match), game: pretty(game) } as Record<Part, string>
  }, [decision, step, briefing, questions])
  // Only the question can be changed: the state and the briefing are always the recorded ones.
  const draft = (which: Part) => (which === "question" ? drafts[step] : undefined) ?? originals[which]
  const text = draft(part)
  const edited = (which: Part) => draft(which) !== originals[which]
  const setDraft = (next: string) => setDrafts({ ...drafts, [step]: next === originals.question ? undefined : next })
  // The form edits the same text the JSON view shows, so switching between the two loses nothing.
  let parsed: Record<string, unknown> | null = null
  try {
    const value = JSON.parse(text)
    parsed = value && typeof value === "object" && !Array.isArray(value) ? value : null
  } catch {}

  const run = async () => {
    setProblem(null)
    let asked: Asked
    let reading: Part = "question"
    try {
      const parsed = {} as Record<Part, Record<string, unknown>>
      for (reading of PARTS) parsed[reading] = JSON.parse(draft(reading))
      // The same order the bot sends: the step's context, then the briefing, then the match.
      const { strategy, playing, ...match } = parsed.state
      asked = { state: { ...(playing ? { playing } : {}), ...(strategy ? { strategy } : {}), game: parsed.game, ...match }, questions: parsed.question as Asked["questions"] }
    } catch (error) {
      setPart(reading)
      return setProblem(`The ${PART_TITLE[reading]} JSON does not parse: ${(error as Error).message}`)
    }
    setBusy(true)
    const started = performance.now()
    try {
      const reply = await fetch("/api/jev", { method: "POST", headers: { "Content-Type": "application/json", Authorization: `Bearer ${key.trim()}` }, body: JSON.stringify(asked) })
      const body = await reply.json().catch(() => null)
      const found = body?.answers?.[Object.keys(asked.questions ?? {})[0]]
      if (!reply.ok || !found?.probabilities) setProblem(reply.status === 401 || reply.status === 403 ? "That key was not accepted." : `Jev did not answer (${reply.status}): ${JSON.stringify(body)?.slice(0, 200) ?? "no details"}`)
      else setResults({ ...results, [step]: { choice: found.choice, odds: found.probabilities, ms: Math.round(performance.now() - started) } })
    } catch {
      setProblem("The request could not be sent.")
    } finally {
      setBusy(false)
    }
  }

  const result = results[step]
  const before = decision[`${step}_probabilities` as const]
  const was = decision[`${step}_choice` as const]
  return (
    <Dialog onOpenChange={(open) => open && onOpen?.()}>
      <DialogTrigger render={<Button variant="outline" size="sm" className="gap-1.5" />}>
        <FlaskConical className="size-3.5" /> Re-ask Jev
      </DialogTrigger>
      <DialogContent className="flex max-h-[92dvh] flex-col gap-3 overflow-hidden sm:max-w-5xl">
        <DialogHeader>
          <DialogTitle>Re-ask Jev at this decision</DialogTitle>
          <DialogDescription>
            This is exactly what was sent. The match state stays as it was recorded; what you can change is the question: its instructions, an option, a{" "}
            <code>not_for</code>. Ask again with your own TypeSafe key to see what Jev would choose at this same moment. One click is one request on your key.
          </DialogDescription>
        </DialogHeader>
        <div className="flex flex-wrap items-end gap-3">
          <Tabs value={step} onValueChange={(value) => setStep(value as Step)}>
            <TabsList>
              {steps.map((name) => (
                <TabsTrigger key={name} value={name}>{STEP_TITLE[name]}</TabsTrigger>
              ))}
            </TabsList>
          </Tabs>
          <div className="flex min-w-56 flex-1 flex-col gap-1">
            <Label htmlFor="typesafe-key" className="gap-1 text-xs text-muted-foreground"><KeyRound className="size-3" /> Your TypeSafe API key — used for this request only, never stored</Label>
            <Input id="typesafe-key" type="password" autoComplete="off" spellCheck={false} value={key} onChange={(event) => setKey(event.target.value)} placeholder="paste your key" />
          </div>
        </div>
        <div className="grid min-h-0 flex-1 gap-4 overflow-y-auto lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)] lg:overflow-hidden">
          <div className="flex min-h-0 flex-col gap-1.5">
            <div className="flex items-center justify-between gap-2">
              <Tabs value={part} onValueChange={(value) => setPart(value as Part)}>
                <TabsList>
                  {PARTS.map((name) => (
                    <TabsTrigger key={name} value={name} className="gap-1.5">
                      {name !== "question" && <Lock aria-label="read-only" className="size-3 text-muted-foreground" />}
                      {PART_TITLE[name]} {edited(name) && <span aria-label="edited" className="size-1.5 rounded-full bg-jev" />}
                    </TabsTrigger>
                  ))}
                </TabsList>
              </Tabs>
              <Tabs value={asJson ? "json" : "form"} onValueChange={(value) => setAsJson(value === "json")} className={cn("ml-auto", part !== "question" && "invisible")}>
                <TabsList aria-label="How to edit the request">
                  <TabsTrigger value="form">Form</TabsTrigger>
                  <TabsTrigger value="json">JSON</TabsTrigger>
                </TabsList>
              </Tabs>
              <Button variant="ghost" size="sm" className={cn("h-7 gap-1 text-xs", part !== "question" && "invisible")} disabled={!edited("question")} onClick={() => setDrafts({ ...drafts, [step]: undefined })}>
                <RotateCcw className="size-3" /> As recorded
              </Button>
            </div>
            {part !== "question" ? (
              <div className="flex min-h-72 flex-1 flex-col gap-2 overflow-hidden lg:min-h-0">
                <p className="flex items-center gap-1.5 text-xs text-muted-foreground"><Lock className="size-3" /> {LOCKED[part]}</p>
                <pre className="min-h-0 flex-1 overflow-auto whitespace-pre-wrap rounded-lg border bg-muted/30 p-3 font-mono text-xs leading-relaxed">{text}</pre>
              </div>
            ) : asJson ? (
  <Textarea id="asked" aria-label={`${PART_TITLE[part]}, as JSON`} spellCheck={false} value={text} onChange={(event) => setDraft(event.target.value)} className="min-h-72 flex-1 resize-none font-mono text-xs leading-relaxed lg:min-h-0" />
            ) : parsed ? (
              <div className="min-h-72 flex-1 overflow-y-auto rounded-lg border p-3 lg:min-h-0">
                <QuestionForm value={parsed as Parameters<typeof QuestionForm>[0]["value"]} onChange={(next) => setDraft(JSON.stringify(next, null, 2))} />

              </div>
            ) : (
              <p className="rounded-lg border border-warn/40 bg-warn/10 p-3 text-sm text-warn-fg">This part is not valid JSON right now, so it cannot be shown as a form. Switch to JSON to fix it, or press As recorded.</p>
            )}
          </div>
          <div className="flex min-h-0 flex-col gap-3 lg:overflow-y-auto">
            <Button onClick={run} disabled={busy || !key.trim()} className="gap-2">
              {busy ? <Loader2 className="size-4 animate-spin" /> : <FlaskConical className="size-4" />} Ask Jev · 1 request
            </Button>
            {problem && <p className="rounded-md border border-bad/40 bg-bad/10 px-3 py-2 text-sm text-bad-fg">{problem}</p>}
            <div className="text-sm">
              <span className="text-muted-foreground">Recorded:</span> <span className="font-medium capitalize">{nice(was)}</span>{" "}
              <span className="tabular-nums text-muted-foreground">{before && was ? `${Math.round((before[was] ?? 0) * 100)}%` : ""}</span>
            </div>
            {result ? (
              <>
                <div className="text-sm">
                  <span className="text-muted-foreground">Now:</span> <span className={cn("font-semibold capitalize", result.choice !== was && "text-jev-fg")}>{nice(result.choice)}</span>{" "}
                  <span className="tabular-nums text-muted-foreground">{Math.round((result.odds[result.choice] ?? 0) * 100)}% · {result.ms} ms</span>
                  {result.choice !== was && <Badge className="ml-2 bg-jev/20 text-jev-fg">changed</Badge>}
                </div>
                <Compare before={before} after={result} />
                <p className="text-xs text-muted-foreground">The last column is the change from the recorded answer, in points. Asking the same thing twice can move a few points by itself.</p>
              </>
            ) : (
              <p className="text-sm text-muted-foreground">The new answer appears here, next to the recorded one.</p>
            )}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}
