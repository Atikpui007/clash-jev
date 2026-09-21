"use client"

import { AlertTriangle, Check, Hourglass, ShieldAlert } from "lucide-react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Item, ItemContent, ItemDescription, ItemGroup, ItemMedia, ItemTitle } from "@/components/ui/item"
import { ScrollArea } from "@/components/ui/scroll-area"
import { cn } from "@/lib/utils"
import { clock, type Decision, nice, played } from "@/lib/replay"

// What became of a decision. "declined" means the pick could not be carried out (a card it cannot afford, a spell
// with nothing to cast it on), so nothing was tapped.
type Kind = "played" | "declined" | "fallback" | "waited"
const kindOf = (d: Decision): Kind => (d.source !== "jev" ? "fallback" : played(d) ? "played" : d.card_choice ? "declined" : "waited")

const LOOK: Record<Kind, { icon: typeof Check; bar: string; text: string; label: string }> = {
  played: { icon: Check, bar: "bg-ok", text: "text-ok-fg", label: "played" },
  declined: { icon: ShieldAlert, bar: "bg-warn", text: "text-warn-fg", label: "declined by code" },
  fallback: { icon: AlertTriangle, bar: "bg-bad", text: "text-bad-fg", label: "Jev failed · fallback" },
  waited: { icon: Hourglass, bar: "bg-muted-foreground/30", text: "text-muted-foreground", label: "waited" },
}

/** Why code did not carry out Jev's pick, without the part the line already says. */
const reason = (note?: string) => (note ?? "").replace(/^Jev chose [^,]+, which /, "").replace(/^cannot be played right now: /, "")

type Line = { kind: Kind; decision: Decision; from: number; count: number }

/** The log so far, newest first: what Jev did, what code had to decline, and where it simply waited. */
export function Timeline({ decisions, current, onSeek }: { decisions: Decision[]; current: number; onSeek?: (time: number) => void }) {
  const lines: Line[] = []
  for (let index = 0; index <= current; index++) {
    const decision = decisions[index]
    const kind = kindOf(decision)
    const last = lines[lines.length - 1]
    // Waiting several snapshots in a row under one strategy is one line.
    if (kind === "waited" && last?.kind === "waited" && last.decision.strategy_choice === decision.strategy_choice) {
      last.count += 1
      last.decision = decision
    } else lines.push({ kind, decision, from: decision.state_elapsed, count: 1 })
  }
  lines.reverse()
  const total = (kind: Kind) => decisions.slice(0, current + 1).filter((d) => kindOf(d) === kind).length
  return (
    <Card className="flex min-h-0 flex-[3] flex-col gap-2 py-4 max-lg:h-96 max-lg:flex-none">
      <CardHeader className="shrink-0 px-5">
        <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1">
          <CardTitle className="text-sm font-medium uppercase tracking-wider text-muted-foreground">Decisions</CardTitle>
          <div className="flex items-center gap-3 text-xs">
            {(["played", "declined", "fallback"] as Kind[]).map((kind) => (
              <span key={kind} className={cn("flex items-center gap-1", LOOK[kind].text, total(kind) === 0 && "opacity-40")}>
                <span className={cn("size-2 rounded-full", LOOK[kind].bar)} />
                <span className="tabular-nums">{total(kind)}</span> {LOOK[kind].label}
              </span>
            ))}
          </div>
        </div>
      </CardHeader>
      <CardContent className="min-h-0 flex-1 px-2">
        <ScrollArea className="h-full">
          <ItemGroup className="gap-1 px-2 pb-20">
            {lines.length === 0 && <p className="px-2 py-3 text-sm text-muted-foreground">Nothing decided yet.</p>}
            {lines.map((line, index) => {
              const { icon: Icon, bar, text } = LOOK[line.kind]
              const d = line.decision
              return (
                <Item
                  key={`${line.from}-${line.kind}`}
                  size="xs"
                  render={onSeek ? <button type="button" onClick={() => onSeek(line.from)} /> : undefined}
                  className={cn(
                    "relative flex-nowrap items-start overflow-hidden py-1.5 pl-4 text-left hover:bg-muted",
                    index === 0 && "bg-muted ring-1 ring-jev/40",
                    line.kind === "played" && "bg-ok/[0.07]",
                    line.kind === "declined" && "bg-warn/[0.06]",
                    line.kind === "fallback" && "bg-bad/10",
                  )}
                >
                  <span className={cn("absolute inset-y-0 left-0 w-1", bar)} />
                  <ItemMedia className="gap-2.5">
                    <time className="w-10 tabular-nums text-muted-foreground">{clock(line.from)}</time>
                    <Icon className={cn("size-4", text)} />
                  </ItemMedia>
                  <ItemContent className="gap-0.5">
                    {line.kind === "played" && (
                      <ItemTitle className="capitalize">
                        {d.action.split(" -> ").map(nice).join(" → ")}
                        <span className="font-normal text-muted-foreground">· {nice(d.strategy_choice)}</span>
                      </ItemTitle>
                    )}
                    {line.kind === "declined" && (
                      <>
                        <ItemTitle className="font-normal">
                          Jev picked <span className="font-semibold capitalize">{nice(d.card_choice)}</span>
                          <span className="capitalize text-muted-foreground">· {nice(d.strategy_choice)}</span>
                        </ItemTitle>
                        <ItemDescription className="text-xs text-warn-fg/80">Code did not play it: {reason(d.note) || "it could not be played"}</ItemDescription>
                      </>
                    )}
                    {line.kind === "fallback" && (
                      <>
                        <ItemTitle className="capitalize">{played(d) ? d.action.split(" -> ").map(nice).join(" → ") : "nothing played"}</ItemTitle>
                        <ItemDescription className="text-xs text-bad-fg/80">The request to Jev failed, so the built-in fallback decided this one.</ItemDescription>
                      </>
                    )}
                    {line.kind === "waited" && (
                      <ItemTitle className="font-normal capitalize text-muted-foreground">
                        {nice(d.strategy_choice) || "no play"}
                        {line.count > 1 && <span className="normal-case tabular-nums">· {line.count} snapshots in a row</span>}
                      </ItemTitle>
                    )}
                  </ItemContent>
                </Item>
              )
            })}
          </ItemGroup>
        </ScrollArea>
      </CardContent>
    </Card>
  )
}
