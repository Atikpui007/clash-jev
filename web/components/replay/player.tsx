"use client"

import type { RefObject } from "react"
import { Slider } from "@/components/ui/slider"
import { cn } from "@/lib/utils"
import { type Decision, played } from "@/lib/replay"
import { Overlay } from "./overlay"

/** The match video with what the bot saw drawn over it, and a scrub bar that carries a tick for every decision. */
export function Player({
  videoRef,
  src,
  decisions,
  current,
  time,
  duration,
  overlay,
  onSeek,
}: {
  videoRef: RefObject<HTMLVideoElement | null>
  src: string
  decisions: Decision[]
  current: Decision | null
  time: number
  duration: number
  overlay: boolean
  onSeek: (time: number) => void
}) {
  const justPlayed = current && played(current) && current.square_xy && time - current.state_elapsed < 2.5 ? current : null
  return (
    <figure className="flex min-h-0 flex-col gap-1">
      <div className="relative mx-auto w-full max-lg:max-w-[calc(58dvh*0.625)] aspect-[5/8] overflow-hidden rounded-xl border bg-black">
        <video ref={videoRef} src={src} playsInline muted preload="auto" className="block size-full object-cover" />
        <Overlay units={current?.units ?? []} show={overlay} square={justPlayed?.square_xy} placed={justPlayed?.action.split(" -> ")[0]} />
      </div>
      <div className="relative h-10 w-full shrink-0">
        {decisions.map((decision, index) => (
          <span
            key={index}
            aria-hidden
            className={cn("pointer-events-none absolute w-px", played(decision) ? "top-1 h-8 w-0.5 bg-jev" : decision.card_choice ? "top-2.5 h-5 bg-warn/60" : "top-3.5 h-3 bg-muted-foreground/40")}
            style={{ left: `${(decision.state_elapsed / Math.max(1, duration)) * 100}%` }}
          />
        ))}
        <Slider
          aria-label="Position in the match"
          className="absolute inset-x-0 top-1/2 -translate-y-1/2 [&_[data-slot=slider-range]]:bg-jev/70 [&_[data-slot=slider-thumb]]:size-4 [&_[data-slot=slider-thumb]]:bg-jev [&_[data-slot=slider-track]]:h-1.5"
          min={0}
          max={Math.max(1, duration)}
          step={0.1}
          value={[Math.min(time, Math.max(1, duration))]}
          onValueChange={(value) => onSeek(Array.isArray(value) ? value[0] : value)}
        />
      </div>
    </figure>
  )
}
