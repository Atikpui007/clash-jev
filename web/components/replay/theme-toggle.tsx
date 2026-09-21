"use client"

import { useSyncExternalStore } from "react"
import { Moon, Sun } from "lucide-react"
import { Button } from "@/components/ui/button"

// The theme lives on <html class="dark"> and in localStorage; this reads it as an external store, so there is no
// state to keep in step and nothing to mismatch while the page loads.
const listeners = new Set<() => void>()
const subscribe = (notify: () => void) => (listeners.add(notify), () => void listeners.delete(notify))
const isDark = () => document.documentElement.classList.contains("dark")

export function ThemeToggle() {
  const dark = useSyncExternalStore(subscribe, isDark, () => true)
  const flip = () => {
    document.documentElement.classList.toggle("dark", !dark)
    try {
      localStorage.setItem("theme", dark ? "light" : "dark")
    } catch {}
    listeners.forEach((notify) => notify())
  }
  return (
    <Button size="icon" variant="ghost" onClick={flip} title={dark ? "Light mode" : "Dark mode"} aria-label={dark ? "Switch to light mode" : "Switch to dark mode"}>
      {dark ? <Sun className="size-4" /> : <Moon className="size-4" />}
    </Button>
  )
}
