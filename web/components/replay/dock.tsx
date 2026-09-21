"use client"

import { Eye, EyeOff, Pause, Play, SkipBack, SkipForward } from "lucide-react"
import { Button } from "@/components/ui/button"
import { clock } from "@/lib/replay"
import { FloatingControls } from "./floating-controls"

const SPEEDS = [0.5, 1, 2]

/** The floating controls, bottom right. In a replay they drive the video. */
export function Dock({
  playing,
  time,
  duration,
  speed,
  overlay,
  onToggle,
  onPlay,
  onSpeed,
  onOverlay,
}: {
  playing: boolean
  time: number
  duration: number
  speed: number
  overlay: boolean
  onToggle: () => void
  onPlay: (direction: -1 | 1) => void
  onSpeed: (speed: number) => void
  onOverlay: () => void
}) {
  return (
    <FloatingControls
      label="Playback"
      primary={
        <Button size="icon" className="size-14 rounded-full" onClick={onToggle} title="play / pause (space)">
          {playing ? <Pause className="size-6" /> : <Play className="size-6" />}
        </Button>
      }
    >
      <span className="rounded-full bg-background/85 px-3 py-1.5 text-sm tabular-nums text-muted-foreground shadow-lg shadow-black/30 backdrop-blur">
        {clock(time)} / {clock(duration)}
      </span>
      <Button size="icon" variant="secondary" className="size-10 rounded-full" onClick={() => onPlay(-1)} title="previous card played (←)">
        <SkipBack className="size-4" />
      </Button>
      <Button size="icon" variant="secondary" className="size-10 rounded-full" onClick={() => onPlay(1)} title="next card played (→)">
        <SkipForward className="size-4" />
      </Button>
      <Button variant="secondary" className="h-10 w-14 rounded-full tabular-nums" onClick={() => onSpeed(SPEEDS[(SPEEDS.indexOf(speed) + 1) % SPEEDS.length])} title="speed">
        {speed}×
      </Button>
      <Button size="icon" variant="secondary" className="size-10 rounded-full" onClick={onOverlay} title="show what the bot saw">
        {overlay ? <Eye className="size-4" /> : <EyeOff className="size-4" />}
      </Button>
    </FloatingControls>
  )
}
