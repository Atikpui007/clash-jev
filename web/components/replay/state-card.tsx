"use client"

import { Droplet, Plane, Skull } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Item, ItemActions, ItemContent, ItemDescription, ItemGroup, ItemMedia, ItemTitle } from "@/components/ui/item"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { cn } from "@/lib/utils"
import { nice, type SentState, type Troop } from "@/lib/replay"
import { Disclosure } from "./disclosure"
import { Meter } from "./meter"

function Elixir({ amount }: { amount: number }) {
  return (
    <div className="flex items-center gap-2">
      <Droplet className="size-5 fill-elixir text-elixir-fg" />
      <div className="flex gap-0.5">
        {Array.from({ length: 10 }, (_, index) => (
          <span key={index} className={cn("h-4 w-6 rounded-sm", index < amount ? "bg-elixir" : "bg-muted")} />
        ))}
      </div>
      <span className="text-lg font-semibold tabular-nums">{amount}</span>
    </div>
  )
}

function Tower({ label, value, mine }: { label: string; value: number | string; mine: boolean }) {
  const health = typeof value === "number" ? value : null
  const down = health === 0
  return (
    <Item variant="outline" size="xs" className={cn("flex-col items-stretch gap-1.5", down && "border-dashed opacity-50")}>
      <ItemContent className="flex-row items-center justify-between text-xs text-muted-foreground">
        <span>{label}</span>
        {down ? <Skull className="size-3" /> : <span className="tabular-nums">{health === null ? "–" : `${Math.round(health * 100)}%`}</span>}
      </ItemContent>
      <Meter value={health ?? 0} tone={mine ? "mine" : "enemy"} />
    </Item>
  )
}

function Troops({ title, troops, mine }: { title: string; troops: Troop[]; mine: boolean }) {
  return (
    <section>
      <h3 className="mb-1.5 text-xs font-medium uppercase tracking-wider text-muted-foreground">
        {title} <span className="tabular-nums">· {troops.length}</span>
      </h3>
      {troops.length === 0 ? (
        <p className="text-sm text-muted-foreground">none seen</p>
      ) : (
        <ItemGroup className="gap-1">
          {troops.map((troop, index) => {
            const tiles = troop.tiles_from_my_tower ?? troop.tiles_from_enemy_tower
            return (
              <Item key={index} variant="muted" size="xs" className="py-1">
                <ItemMedia>
                  <span className={cn("size-2 rounded-full", mine ? "bg-mine" : "bg-enemy")} />
                </ItemMedia>
                <ItemContent>
                  <ItemTitle className="capitalize">
                    {nice(troop.troop)}
                    {troop.archetypes?.includes("air troop") && <Plane className="size-3 text-muted-foreground" />}
                  </ItemTitle>
                </ItemContent>
                <ItemActions className="gap-2.5 text-sm text-muted-foreground">
                  {troop.archetypes?.[0] && <span className="hidden 2xl:inline">{troop.archetypes[0]}</span>}
                  <span>{troop.lane} · {troop.where}</span>
                  {tiles !== undefined && <span className="tabular-nums">{tiles} tiles</span>}
                  <span className="w-10 text-right tabular-nums text-foreground">{Math.round(troop.health_remaining * 100)}%</span>
                </ItemActions>
              </Item>
            )
          })}
        </ItemGroup>
      )}
    </section>
  )
}

/** Everything Jev was told about the match at this instant. */
export function StateCard({ state, briefing, empty }: { state: SentState | null; briefing: Record<string, unknown> | null; empty?: string }) {
  if (!state)
    return (
      <Card className="flex min-h-0 flex-[5] flex-col gap-3 py-4">
        <CardHeader className="shrink-0 px-5">
          <CardTitle className="text-sm font-medium uppercase tracking-wider text-muted-foreground">Game state</CardTitle>
        </CardHeader>
        <CardContent className="grid flex-1 place-items-center px-5 text-center text-sm text-muted-foreground">{empty ?? "Nothing has been read from the screen yet."}</CardContent>
      </Card>
    )
  const towers = state.towers
  return (
    <Card className="flex min-h-0 flex-[5] flex-col gap-3 py-4 max-lg:max-h-[32rem] max-lg:flex-none">
      <CardHeader className="shrink-0 px-5">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm font-medium uppercase tracking-wider text-muted-foreground">Game state</CardTitle>
          <span className="text-sm text-muted-foreground">{state.clock.elixir_rate} elixir · enemy elixir ≈ {state.enemy_elixir_estimate ?? "–"}</span>
        </div>
      </CardHeader>
      <CardContent className="min-h-0 flex-1 space-y-3 overflow-y-auto px-5">
        <Elixir amount={state.elixir} />
        <ItemGroup className="grid grid-cols-4 gap-2">
          {state.hand.map((card, index) => {
            const short = card.elixir_cost !== null && card.elixir_cost > state.elixir
            return (
              <Item key={index} variant={short ? "outline" : "muted"} size="xs" className={cn("flex-nowrap items-start py-1.5", short && "border-dashed opacity-55")}>
                <ItemContent className="min-w-0 gap-0">
                  <ItemTitle className="w-full justify-between gap-1 capitalize leading-tight">
                    <span className="truncate">{nice(card.card)}</span>
                    <Badge className="size-5 shrink-0 rounded-full bg-elixir/25 p-0 text-xs font-semibold text-elixir-fg">{card.elixir_cost ?? "?"}</Badge>
                  </ItemTitle>
                  <ItemDescription className="truncate text-xs">{card.class ?? card.type ?? "not recognised"}</ItemDescription>
                </ItemContent>
              </Item>
            )
          })}
        </ItemGroup>
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          next card <Badge variant="outline" className="capitalize">{nice(state.next_card)}</Badge>
        </div>
        <section aria-label="Towers" className="space-y-1.5">
          <div className="grid grid-cols-3 gap-1.5">
            <Tower label="their left" value={towers.enemy_left} mine={false} />
            <Tower label="their king" value={towers.enemy_king} mine={false} />
            <Tower label="their right" value={towers.enemy_right} mine={false} />
          </div>
          <div className="grid grid-cols-3 gap-1.5">
            <Tower label="my left" value={towers.my_left} mine />
            <Tower label="my king" value={towers.my_king} mine />
            <Tower label="my right" value={towers.my_right} mine />
          </div>
        </section>
        <Troops title="Enemy troops" troops={state.enemy_troops} mine={false} />
        <Troops title="My troops" troops={state.my_troops ?? []} mine />
        <Disclosure label="State JSON">
          <pre className="max-h-96 overflow-auto rounded-lg border bg-muted/30 p-3 text-xs leading-relaxed">{JSON.stringify(state, null, 2)}</pre>
        </Disclosure>
        {briefing && (
          <Disclosure label="Game briefing">
            <pre className="max-h-96 overflow-auto whitespace-pre-wrap rounded-lg border bg-muted/30 p-3 text-xs leading-relaxed">{JSON.stringify(briefing, null, 2)}</pre>
          </Disclosure>
        )}
      </CardContent>
    </Card>
  )
}
