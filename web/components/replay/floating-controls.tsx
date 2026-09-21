"use client"

import { type PointerEvent, type ReactNode, useRef, useState } from "react"
import { ChevronLeft, GripVertical } from "lucide-react"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"

type Offset = { x: number; y: number }
const REMEMBERED = "controls-position"

function remembered(): Offset {
  try {
    const saved = JSON.parse(localStorage.getItem(REMEMBERED) ?? "null")
    if (saved && Number.isFinite(saved.x) && Number.isFinite(saved.y)) return saved
  } catch {}
  return { x: 0, y: 0 }
}

/**
 * Controls that float over the page and fold away. They start bottom right, can be dragged anywhere by the grip
 * (double-click it to send them home), and stay where they were put. The primary button (play / pause,
 * Start / Stop) is always there, so folding the rest can never put it out of reach.
 */
export function FloatingControls({ label, primary, children }: { label: string; primary: ReactNode; children: ReactNode }) {
  const [open, setOpen] = useState(false)
  const [offset, setOffset] = useState<Offset>(remembered)
  const [dragging, setDragging] = useState(false)
  const bar = useRef<HTMLElement>(null)
  const grabbed = useRef<{ pointer: Offset; offset: Offset } | null>(null)

  const place = (next: Offset, save = false) => {
    // Kept on screen: the bar may go anywhere, but never further than its own edge.
    const box = bar.current?.getBoundingClientRect()
    if (box) {
      const home = { right: box.right - offset.x, bottom: box.bottom - offset.y, width: box.width, height: box.height }
      next = {
        x: Math.min(window.innerWidth - home.right - 4, Math.max(4 - (home.right - home.width), next.x)),
        y: Math.min(window.innerHeight - home.bottom - 4, Math.max(4 - (home.bottom - home.height), next.y)),
      }
    }
    setOffset(next)
    if (save)
      try {
        localStorage.setItem(REMEMBERED, JSON.stringify(next))
      } catch {}
  }
  const onDown = (event: PointerEvent<HTMLButtonElement>) => {
    event.currentTarget.setPointerCapture(event.pointerId)
    grabbed.current = { pointer: { x: event.clientX, y: event.clientY }, offset }
    setDragging(true)
  }
  const moved = (event: PointerEvent<HTMLButtonElement>): Offset | null =>
    grabbed.current && {
      x: grabbed.current.offset.x + event.clientX - grabbed.current.pointer.x,
      y: grabbed.current.offset.y + event.clientY - grabbed.current.pointer.y,
    }

  return (
    <nav
      ref={bar}
      aria-label={label}
      style={{ transform: `translate(${offset.x}px, ${offset.y}px)` }}
      className={cn(
        "pointer-events-none fixed bottom-5 right-5 z-50 flex items-center gap-2 [&_button]:pointer-events-auto [&_button]:shadow-lg [&_button]:shadow-black/30",
        dragging && "select-none",
      )}
    >
      <Button
        size="icon"
        variant="secondary"
        className={cn("size-9 touch-none rounded-full", dragging ? "cursor-grabbing" : "cursor-grab")}
        title="Drag to move · double-click to send back to the corner"
        aria-label="Move the controls"
        onPointerDown={onDown}
        onPointerMove={(event) => {
          const next = moved(event)
          if (next) place(next)
        }}
        onPointerUp={(event) => {
          const next = moved(event)
          grabbed.current = null
          setDragging(false)
          if (next) place(next, true)
        }}
        onDoubleClick={() => place({ x: 0, y: 0 }, true)}
      >
        <GripVertical className="size-4" />
      </Button>
      <div
        aria-hidden={!open}
        className={cn("flex items-center gap-2 transition-all duration-200 ease-out", open ? "translate-x-0 opacity-100" : "pointer-events-none w-0 translate-x-6 overflow-hidden opacity-0 [&_button]:!pointer-events-none")}
      >
        {children}
      </div>
      {primary}
      <Button size="icon" variant="secondary" className="size-9 rounded-full" onClick={() => setOpen(!open)} aria-expanded={open} title={open ? "Fold the controls away" : "More controls"}>
        <ChevronLeft className={cn("size-4 transition-transform duration-200", open && "rotate-180")} />
      </Button>
    </nav>
  )
}
