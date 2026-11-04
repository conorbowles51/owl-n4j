import { useEffect, useRef, useState } from "react"
import { Button } from "@/components/ui/button"
import { landing, short, type DateLanding, type DayCount } from "./go-to-date"

/** The visible Go to date control beside the `g` key (03 section 3.9, D-27). */
export function GoToDate({
  days,
  where,
  noun,
  onGo,
  open,
  onOpenChange,
}: {
  days: DayCount[]
  where: string
  noun?: string
  onGo: (day: string) => void
  open: boolean
  onOpenChange: (v: boolean) => void
}) {
  const [value, setValue] = useState("")
  const [miss, setMiss] = useState<Extract<DateLanding, { kind: "none" }> | null>(null)
  const box = useRef<HTMLInputElement>(null)
  useEffect(() => {
    if (open) box.current?.focus()
  }, [open])
  const go = (day: string) => {
    const l = landing(days, day, where, noun)
    if (l.kind === "day") {
      setMiss(null)
      onGo(day)
    } else setMiss(l)
  }
  return (
    <span className="flex flex-wrap items-center gap-1 text-xs">
      <Button size="sm" variant="outline" aria-expanded={open} onClick={() => onOpenChange(!open)}>
        Go to date <kbd className="ml-1 text-xs text-muted-foreground">g</kbd>
      </Button>
      {open && (
        <form
          className="flex items-center gap-1"
          onSubmit={(e) => {
            e.preventDefault()
            if (/^\d{4}-\d{2}-\d{2}$/.test(value)) go(value)
          }}
        >
          <input
            ref={box}
            type="date"
            aria-label="Date to go to"
            className="rounded border bg-background px-1 py-0.5"
            value={value}
            onChange={(e) => {
              setValue(e.target.value)
              setMiss(null)
            }}
            onKeyDown={(e) => {
              if (e.key === "Escape") onOpenChange(false)
            }}
          />
          <Button type="submit" size="sm" variant="ghost" disabled={!value}>
            Go
          </Button>
        </form>
      )}
      {miss && (
        <span role="status">
          {miss.words}{" "}
          {miss.before && (
            <button type="button" className="underline underline-offset-2" onClick={() => { setMiss(null); onGo(miss.before!.day) }}>
              Go to {short(miss.before.day)}
            </button>
          )}
          {miss.before && miss.after && " "}
          {miss.after && (
            <button type="button" className="underline underline-offset-2" onClick={() => { setMiss(null); onGo(miss.after!.day) }}>
              Go to {short(miss.after.day)}
            </button>
          )}
        </span>
      )}
    </span>
  )
}
