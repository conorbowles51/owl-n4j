import { useState } from "react"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import { getRecord } from "../api"
import { originalLines, type TimeCellProps } from "../lib/time-cell"
import type { RecordDetail } from "../schemas"

/**
 * A row's time (03 section 3.2): minutes in the row, the full form with seconds on hover, and the original value on
 * demand (click, or focus and press "o"): what the report wrote, byte for byte, the offset stored, the field, and
 * the zone used with its basis.
 */

export function TimeCell(props: TimeCellProps) {
  const [open, setOpen] = useState(false)
  const [detail, setDetail] = useState<RecordDetail | null>(null)
  const load = () => {
    if (!detail) void getRecord(props.caseId, props.recordUid, props.zone).then(setDetail).catch(() => undefined)
  }
  return (
    <Popover
      open={open}
      onOpenChange={(o) => {
        setOpen(o)
        if (o) load()
      }}
    >
      <PopoverTrigger asChild>
        <button
          type="button"
          className="whitespace-nowrap text-xs tabular-nums text-muted-foreground hover:underline"
          title={props.time.full}
          data-time-cell
          onKeyDown={(e) => {
            if (e.key === "o") {
              e.preventDefault()
              setOpen(true)
              load()
            }
          }}
        >
          {props.time.row}
          {props.time.zone_decided && <span className="ml-1 italic">zone by decision</span>}
        </button>
      </PopoverTrigger>
      <PopoverContent className="w-[28rem] text-xs" aria-label="Original time value">
        <dl className="grid grid-cols-[max-content_1fr] gap-x-3 gap-y-1">
          {originalLines(detail, props).map((l) => (
            <div key={l.label} className="contents">
              <dt className="text-muted-foreground">{l.label}</dt>
              <dd className="break-all font-mono" data-line={l.label}>
                {l.value}
              </dd>
            </div>
          ))}
        </dl>
      </PopoverContent>
    </Popover>
  )
}

