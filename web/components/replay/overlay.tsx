import { cn } from "@/lib/utils"
import { type Decision, nice } from "@/lib/replay"

/** What the bot saw, drawn over the picture: a marker and a name per troop, and the square Jev just played on. */
export function Overlay({ units, show, square, placed }: { units: Decision["units"]; show: boolean; square?: [number, number] | null; placed?: string }) {
  return (
    <>
      {show && (
        <div className="pointer-events-none absolute inset-0">
          {units.map((unit, index) => (
            <div key={index} className="absolute -translate-x-1/2" style={{ left: `${unit.x * 100}%`, top: `${unit.y * 100}%` }}>
              <div className={cn("mx-auto size-2.5 rounded-full border-[1.5px]", unit.owner === "enemy" ? "border-rose-400" : "border-sky-400")} />
              {unit.name && (
                <div className={cn("mt-px text-[10px] font-semibold capitalize leading-[1.15] [text-shadow:0_0_2px_rgb(0_0_0),0_1px_2px_rgb(0_0_0)]", unit.owner === "enemy" ? "text-rose-200" : "text-sky-200")}>
                  {nice(unit.name)}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
      {square && (
        // Where Jev's card was just put down, drawn like the troop labels: a small ring and a pill, in green.
        <div className="pointer-events-none absolute -translate-x-1/2 -translate-y-2" style={{ left: `${square[0] * 100}%`, top: `${square[1] * 100}%` }}>
          <div className="relative mx-auto size-3">
            <span className="absolute inset-0 animate-ping rounded-full border-[1.5px] border-green-400" />
            <span className="absolute inset-0 rounded-full border-[1.5px] border-green-400 bg-green-400/25" />
          </div>
          <div className="mt-px text-[10px] font-semibold capitalize leading-[1.15] text-green-200 [text-shadow:0_0_2px_rgb(0_0_0),0_1px_2px_rgb(0_0_0)]">{placed ? nice(placed) : "placed"}</div>
        </div>
      )}
    </>
  )
}
