"use client"

import { Plus, Trash2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { cn } from "@/lib/utils"
import { nice } from "@/lib/replay"

function Remove({ onClick, what }: { onClick: () => void; what: string }) {
  return (
    <Button type="button" variant="ghost" size="icon" className="size-7 shrink-0 text-muted-foreground hover:text-bad-fg" onClick={onClick} title={`Remove ${what}`} aria-label={`Remove ${what}`}>
      <Trash2 className="size-3.5" />
    </Button>
  )
}

type Wording = string | { what?: string; not_for?: string }
type Question = { type?: string; instructions?: string; criteria?: Record<string, Wording> }

/** The one question of a request: its instructions, and every option with what it means and what it is not for. */
export function QuestionForm({ value, onChange }: { value: Record<string, Question>; onChange: (next: Record<string, Question>) => void }) {
  const [name, question] = Object.entries(value)[0] ?? ["question", {}]
  const criteria = question.criteria ?? {}
  const set = (next: Partial<Question>) => onChange({ [name]: { ...question, ...next } })
  // An option is renamed in place, so the order Jev sees the options in does not change.
  const setOption = (option: string, renamed: string, worded: Wording) => set({ criteria: Object.fromEntries(Object.entries(criteria).map(([key, old]) => (key === option ? [renamed, worded] : [key, old]))) })
  return (
    <div className="space-y-4">
      <div className="space-y-1.5">
        <Label htmlFor="instructions" className="text-xs text-muted-foreground">Instructions</Label>
        <Textarea id="instructions" value={question.instructions ?? ""} onChange={(event) => set({ instructions: event.target.value })} className="max-h-48 min-h-24 text-sm leading-relaxed" />
      </div>
      <div className="space-y-2">
        <Label className="text-xs text-muted-foreground">Options · {Object.keys(criteria).length}</Label>
        {Object.entries(criteria).map(([option, worded]) => {
          const parts = typeof worded === "string" ? { what: worded } : worded
          const structured = typeof worded !== "string"
          const word = (next: { what?: string; not_for?: string }) => setOption(option, option, structured || next.not_for !== undefined ? { ...parts, ...next } : (next.what ?? ""))
          return (
            <div key={option} className="space-y-1.5 rounded-lg border bg-muted/20 p-2.5">
              <div className="flex items-center gap-1">
                <Input aria-label="Option name" value={option} onChange={(event) => event.target.value && !(event.target.value in criteria) && setOption(option, event.target.value, worded)} className="h-8 font-mono text-xs font-medium" />
                <Remove onClick={() => set({ criteria: Object.fromEntries(Object.entries(criteria).filter(([key]) => key !== option)) })} what={nice(option)} />
              </div>
              <Textarea aria-label={`What ${option} means`} value={parts.what ?? ""} onChange={(event) => word({ what: event.target.value })} className="min-h-0 text-sm leading-relaxed [field-sizing:content]" />
              {parts.not_for !== undefined ? (
                <div className="space-y-1">
                  <Label className="text-xs text-warn-fg">Not for</Label>
                  <Textarea aria-label={`What ${option} is not for`} value={parts.not_for} onChange={(event) => word({ not_for: event.target.value })} className={cn("min-h-0 text-sm leading-relaxed [field-sizing:content]", "border-warn/30")} />
                </div>
              ) : (
                <Button type="button" variant="ghost" size="sm" className="h-7 gap-1 px-2 text-xs" onClick={() => word({ not_for: "" })}>
                  <Plus className="size-3" /> Add a not_for
                </Button>
              )}
            </div>
          )
        })}
        <Button type="button" variant="outline" size="sm" className="gap-1" onClick={() => set({ criteria: { ...criteria, [`new_option_${Object.keys(criteria).length + 1}`]: "" } })}>
          <Plus className="size-3.5" /> Add an option
        </Button>
      </div>
    </div>
  )
}
