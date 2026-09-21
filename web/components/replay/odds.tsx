"use client"

import { ChevronDown } from "lucide-react"
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible"
import { cn } from "@/lib/utils"
import { nice, type Odds } from "@/lib/replay"
import { Meter } from "./meter"

function Row({ name, odds, chosen }: { name: string; odds: number; chosen: boolean }) {
  return (
    <li className="grid grid-cols-[minmax(0,13rem)_1fr_3rem] items-center gap-3 text-sm">
      <span className={cn("truncate", chosen ? "font-semibold text-foreground" : "text-muted-foreground")}>{nice(name)}</span>
      <Meter value={Math.max(0.015, odds)} tone={chosen ? "violet" : "quiet"} thick />
      <span className="text-right tabular-nums text-muted-foreground">{Math.round(odds * 100)}%</span>
    </li>
  )
}

/** The probability Jev gave every option: the top three, the rest behind a toggle. */
export function OddsBars({ odds, chosen }: { odds: Odds; chosen?: string }) {
  const all = Object.entries(odds).sort((a, b) => b[1] - a[1])
  const rest = all.slice(3)
  return (
    <Collapsible>
      <ul className="space-y-1.5">
        {all.slice(0, 3).map(([name, p]) => (
          <Row key={name} name={name} odds={p} chosen={name === chosen} />
        ))}
      </ul>
      {rest.length > 0 && (
        <>
          <CollapsibleContent>
            <ul className="mt-1.5 space-y-1.5">
              {rest.map(([name, p]) => (
                <Row key={name} name={name} odds={p} chosen={name === chosen} />
              ))}
            </ul>
          </CollapsibleContent>
          <CollapsibleTrigger className="group mt-1.5 flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
            <ChevronDown className="size-3.5 transition-transform group-data-[panel-open]:rotate-180" />
            <span className="group-data-[panel-open]:hidden">{rest.length} more options</span>
            <span className="hidden group-data-[panel-open]:inline">fewer</span>
          </CollapsibleTrigger>
        </>
      )}
    </Collapsible>
  )
}
