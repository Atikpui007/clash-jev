"use client"

import { Camera, Eye, Braces, Compass, Layers, MapPin, Pointer, ChevronRight } from "lucide-react"
import { Item, ItemContent, ItemDescription, ItemMedia, ItemTitle } from "@/components/ui/item"
import { cn } from "@/lib/utils"
import { type Decision, type Stage, STAGES, stageTimes } from "@/lib/replay"

const LABEL: Record<Stage, { title: string; detail: string; icon: typeof Camera }> = {
  capture: { title: "Screen capture", detail: "once a second", icon: Camera },
  vision: { title: "Vision", detail: "OpenCV + troop network", icon: Eye },
  state: { title: "State", detail: "hand · elixir · troops · towers", icon: Braces },
  strategy: { title: "Step 1 · Strategy", detail: "Jev picks 1 of 12", icon: Compass },
  card: { title: "Step 2 · Card", detail: "Jev picks 1 of 4", icon: Layers },
  square: { title: "Step 3 · Square", detail: "Jev picks where", icon: MapPin },
  tap: { title: "Tap", detail: "card, then square", icon: Pointer },
}

/** screen capture -> vision -> state -> step 1 -> step 2 -> step 3 -> tap, with the stage now running lit. */
export function Pipeline({ decision, active, every }: { decision: Decision | null; active: Stage | null; every?: number }) {
  const times = decision ? stageTimes(decision) : []
  return (
    <ol aria-label="What happens to every snapshot" className="flex shrink-0 items-stretch gap-1 rounded-lg border bg-card p-1 max-lg:overflow-x-auto max-lg:[scrollbar-width:none]">
      {STAGES.map((stage, index) => {
        const { title, detail, icon: Icon } = LABEL[stage]
        const ran = times.find((t) => t.stage === stage)?.ran ?? false
        const took = times.find((t) => t.stage === stage)
        const isJev = stage === "strategy" || stage === "card" || stage === "square"
        const lit = active === stage
        return (
          <li key={stage} className="flex min-w-0 flex-1 items-center gap-1 max-lg:flex-none">
            <Item
              variant="outline"
              size="xs"
              aria-current={lit ? "step" : undefined}
              className={cn(
                "min-w-0 flex-1 flex-nowrap gap-2 px-2.5 py-1 transition-all duration-150",
                lit
                  ? isJev
                    ? "border-jev/70 bg-jev/15 shadow-[0_0_0_3px] shadow-jev/15"
                    : "border-ok/70 bg-ok/15 shadow-[0_0_0_3px] shadow-ok/15"
                  : ran
                    ? "bg-muted/40"
                    : "border-dashed opacity-40",
              )}
            >
              <ItemMedia>
                <Icon className={cn("size-4", lit ? (isJev ? "text-jev-fg" : "text-ok-fg") : "text-muted-foreground")} />
              </ItemMedia>
              <ItemContent className="min-w-0 flex-row items-baseline gap-1.5">
                <ItemTitle className="shrink-0 truncate text-[13px]">{title}</ItemTitle>
                <ItemDescription className="ml-1.5 min-w-0 truncate text-xs">
                  {isJev && ran && took
                    ? `${Math.round(took.to - took.from)} ms`
                    : !ran && decision
                      ? "skipped"
                      : stage === "capture" && every
                        ? `every ${every} s`
                        : detail}
                </ItemDescription>
              </ItemContent>
            </Item>
            {index < STAGES.length - 1 && <ChevronRight className="size-3.5 shrink-0 text-muted-foreground/50" />}
          </li>
        )
      })}
    </ol>
  )
}
