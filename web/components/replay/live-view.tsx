"use client"

import { useEffect, useState } from "react"
import { CircleStop, Download, FlaskConical, Laptop, Images, Layers, type LucideIcon, MessageSquare, Play, Settings2, TabletSmartphone, Timer, Unplug } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import { cn } from "@/lib/utils"
import { BOT, command, useLive } from "@/lib/live"
import { stageAt } from "@/lib/replay"
import { FloatingControls } from "./floating-controls"
import { Overlay } from "./overlay"
import { type Mode, Shell } from "./shell"

/** Where the picture would be, when there is none: what is missing and what to do about it. */
function Empty({ icon: Icon, title, hint, code }: { icon: LucideIcon; title: string; hint: string; code: string }) {
  return (
    <div className="grid size-full place-items-center p-8 text-center">
      <div className="max-w-xs space-y-3">
        <div className="mx-auto grid size-14 place-items-center rounded-full bg-muted text-muted-foreground">
          <Icon className="size-7" />
        </div>
        <p className="text-base font-medium">{title}</p>
        <p className="text-sm text-muted-foreground">{hint}</p>
        <code className="inline-block rounded-md border bg-background px-2.5 py-1 text-xs">{code}</code>
      </div>
    </div>
  )
}

const CODE = "https://github.com/bytelabs-oss/clash-jev#setup"

/** On the public site there is no bot to talk to: live mode runs on the visitor's own machine. */
function RunItLocally() {
  return (
    <div className="grid size-full place-items-center overflow-y-auto p-6 text-center">
      <div className="max-w-sm space-y-4">
        <div className="mx-auto grid size-14 place-items-center rounded-full bg-muted text-muted-foreground">
          <Laptop className="size-7" />
        </div>
        <p className="text-base font-medium">Live mode runs on your own machine</p>
        <p className="text-sm text-muted-foreground">
          This site plays back recorded matches. To watch Jev play live, the bot has to run on a computer with an Android device plugged in over USB. It reads the screen and sends
          the taps from there.
        </p>
        <ol className="space-y-2 text-left text-sm text-muted-foreground">
          <li>1. Download the code and install it.</li>
          <li>2. Plug in an Android device with Clash Royale and USB debugging on.</li>
          <li>
            3. Run <code className="rounded-md border bg-background px-1.5 py-0.5 text-xs">clash-jev serve</code> and open{" "}
            <code className="rounded-md border bg-background px-1.5 py-0.5 text-xs">http://127.0.0.1:8765</code>. It is this same page, with the live feed.
          </li>
        </ol>
        <Button render={<a href={CODE} target="_blank" rel="noreferrer" />} className="gap-2">
          <Download className="size-4" /> Get the code
        </Button>
      </div>
    </div>
  )
}

/** The bot on this machine, as it plays: the tablet's picture, and every decision as it is made. */
export function LiveView({ onMode }: { onMode: (mode: Mode) => void }) {
  // Only a page opened on this machine can reach the bot. Anywhere else, say how to run it.
  const [hosted] = useState(() => !["localhost", "127.0.0.1"].includes(window.location.hostname))
  const live = useLive(!hosted)
  const [cap, setCap] = useState(250)
  const [every, setEvery] = useState(1)
  const [now, setNow] = useState(0)
  useEffect(() => {
    let frame = 0
    const tick = () => {
      setNow(performance.now())
      frame = requestAnimationFrame(tick)
    }
    frame = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(frame)
  }, [])

  const decision = live.decisions[live.decisions.length - 1] ?? null
  const active = decision && live.arrivedAt ? stageAt(decision, now - live.arrivedAt) : null
  const running = live.control?.running ?? false
  // A match is on screen when the hand can be read. On a menu the badge reader sees troops in the blue buttons;
  // none of that is a game state, so none of it is shown.
  const inMatch = (live.state?.hand ?? []).filter((card) => card.card !== "unknown").length >= 2
  const justPlayed = decision?.square_xy && now - live.arrivedAt < 2500 ? decision.square_xy : null

  // Three things can be on the screen: the device's picture, "the bot is not running", or "the bot cannot see the
  // device". The last two are shown as a message with what to do about it.
  const message = live.control?.message ?? ""
  const deviceLost = message.startsWith("Cannot read the device")
  const [feedBroken, setFeedBroken] = useState(0) // the boot the feed failed under; a restart of the bot clears it
  const noPicture = hosted || !live.connected || deviceLost || feedBroken === live.boot + 1
  // Worth a line under the screen: progress while collecting, or something that went wrong. Not the last run's log path.
  // A missing device is already said where the picture would be; it is not repeated underneath.
  const caption = !noPicture && (live.control?.mode === "collecting" || /error|cannot/i.test(message)) ? message : null
  const screen = (
    <figure className="flex min-h-0 flex-col gap-2">
      <div className={cn("relative mx-auto w-full max-lg:max-w-[calc(58dvh*0.625)] aspect-[5/8] overflow-hidden rounded-xl border", noPicture ? "border-dashed bg-muted/30" : "bg-black")}>
        {hosted ? (
          <RunItLocally />
        ) : noPicture ? (
          <Empty
            icon={live.connected ? TabletSmartphone : Unplug}
            title={live.connected ? "No device connected" : "The bot is not running"}
            hint={live.connected ? "Plug the tablet in over USB and accept the debugging prompt. The picture comes back by itself." : "Start it on this machine, and this page connects by itself."}
            code={live.connected ? "adb devices" : "clash-jev serve"}
          />
        ) : (
          <>
            {/* A new key after the bot restarts makes the browser reconnect the feed, which it never does by itself. */}
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img key={live.boot} src={`${BOT}/stream.mjpg?boot=${live.boot}`} alt="The device's screen" className="block size-full object-cover" onError={() => setFeedBroken(live.boot + 1)} />
            <Overlay units={inMatch ? live.units : []} show square={justPlayed} placed={decision?.action.split(" -> ")[0]} />
          </>
        )}
      </div>
      {caption && <figcaption className="truncate text-sm text-muted-foreground">{caption}</figcaption>}
    </figure>
  )

  // Between runs: what to do next, and the last run in one line (without the log's path).
  const lastRun = message.match(/Finished: (\d+) cards played, (\d+) decisions, (\d+) Jev requests/)
  const idleLine = running
    ? undefined
    : hosted
      ? "Live decisions appear here when the bot runs on your own machine. The recorded matches are under Replay."
      : lastRun
      ? `Last run: ${lastRun[1]} cards played · ${lastRun[2]} decisions · ${lastRun[3]} Jev requests. It is under Replay once published. Enter a match and press Start for the next one.`
      : "Enter a match, then press Start. Jev's decisions appear here as it makes them."
  const headerRight = (
    <>
      <Badge variant="outline" className={cn("gap-1.5", running && "border-ok/60 text-ok-fg")}>
        <span className={cn("size-2 rounded-full", running ? "animate-pulse bg-ok" : live.connected ? "bg-muted-foreground/60" : "bg-bad")} />
        {live.connected ? (live.control?.mode ?? "idle") : "not connected"}
      </Badge>
      {running && live.control?.mode !== "collecting" && (
        <>
          <Badge variant="outline" className="gap-1"><MessageSquare className="size-3" /> {live.control?.requests ?? 0} / {live.control?.cap} Jev requests</Badge>
          <Badge variant="outline" className="gap-1"><Timer className="size-3" /> {live.control?.decisions ?? 0} decisions</Badge>
          <Badge variant="outline" className="gap-1"><Layers className="size-3" /> {live.control?.cards_played ?? 0} cards played</Badge>
        </>
      )}
    </>
  )

  // Start is the primary button, and turns into Stop while a run is on: folding the rest never hides Stop.
  const idle = !running && live.connected
  const dock = (
    <FloatingControls
      label="Bot controls"
      primary={
        running ? (
          <Button size="lg" className="h-14 rounded-full bg-red-600 px-7 text-base text-white hover:bg-red-500" onClick={() => command("/stop")}>
            <CircleStop className="size-5" /> Stop
          </Button>
        ) : (
          <Button size="lg" className="h-14 rounded-full bg-green-600 px-7 text-base text-white hover:bg-green-500" disabled={!idle} onClick={() => command("/start", { dry_run: false, max_requests: cap, every })} title="Jev plays: start once you are in a match">
            <Play className="size-5" /> Start
          </Button>
        )
      }
    >
      <Button variant="secondary" className="h-10 rounded-full" disabled={!idle} onClick={() => command("/start", { dry_run: true, max_requests: cap, every })} title="Jev decides, nothing is tapped">
        <FlaskConical className="size-4" /> Dry run
      </Button>
      <Button variant="secondary" className="h-10 rounded-full" disabled={!idle} onClick={() => command("/start", { collect: true })} title="You play; the bot only saves pictures for training. No Jev requests.">
        <Images className="size-4" /> Collect
      </Button>
      <Popover>
        <PopoverTrigger render={<Button size="icon" variant="secondary" className="size-10 rounded-full" title="settings" />}>
          <Settings2 className="size-4" />
        </PopoverTrigger>
        <PopoverContent side="top" align="end" className="w-64 space-y-3">
          <label className="flex items-center justify-between gap-3 text-sm">
            Max Jev requests
            <input type="number" min={1} value={cap} onChange={(e) => setCap(Math.max(1, +e.target.value))} className="w-20 rounded-md border bg-background px-2 py-1 text-right tabular-nums" />
          </label>
          <label className="flex items-center justify-between gap-3 text-sm">
            Seconds between snapshots
            <input type="number" min={0.2} step={0.1} value={every} onChange={(e) => setEvery(Math.max(0.2, +e.target.value))} className="w-20 rounded-md border bg-background px-2 py-1 text-right tabular-nums" />
          </label>
        </PopoverContent>
      </Popover>
    </FloatingControls>
  )

  return (
    <Shell
      mode="live"
      onMode={onMode}
      headerRight={hosted ? null : headerRight}
      screen={screen}
      dock={hosted ? null : dock}
      decision={decision}
      picked={live.picked}
      active={active}
      questions={live.questions}
      state={inMatch ? live.state : null}
      noState={hosted ? "The game state appears here when the bot runs on your own machine." : live.connected ? "No match on screen. The game state appears once you are in a battle." : undefined}
      briefing={live.briefing}
      decisions={live.decisions}
      current={live.decisions.length - 1}
      idle={idleLine}
    />
  )
}
