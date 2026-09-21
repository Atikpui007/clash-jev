import { Progress } from "@/components/ui/progress"
import { cn } from "@/lib/utils"

const TONE = {
  violet: "[&_[data-slot=progress-indicator]]:bg-jev",
  quiet: "[&_[data-slot=progress-indicator]]:bg-muted-foreground/40",
  mine: "[&_[data-slot=progress-indicator]]:bg-mine",
  enemy: "[&_[data-slot=progress-indicator]]:bg-enemy",
} as const

/** A shadcn Progress in the colours this page uses: odds, and tower health. `value` is 0-1. */
export function Meter({ value, tone, thick = false, className }: { value: number; tone: keyof typeof TONE; thick?: boolean; className?: string }) {
  return (
    <Progress
      value={Math.round(Math.min(1, Math.max(0, value)) * 100)}
      className={cn(TONE[tone], thick ? "[&_[data-slot=progress-track]]:h-2.5" : "[&_[data-slot=progress-track]]:h-2", className)}
    />
  )
}
