import { useMemo } from "react"
import { RotateCcw } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"

import type { TimelineItem } from "../../types"
import { compactNumber } from "../shared/cellebrite-format"
import { eventColor, eventTimestamp, eventType, parseTs, toDateInput } from "./eventUtils"

export function EventDateScrubber({
  events,
  startDate,
  endDate,
  onWindowChange,
}: {
  events: TimelineItem[]
  startDate: string
  endDate: string
  onWindowChange: (startDate: string, endDate: string) => void
}) {
  const buckets = useMemo(() => buildBuckets(events), [events])
  const max = Math.max(...buckets.map((bucket) => bucket.count), 1)
  const hasWindow = Boolean(startDate || endDate)

  return (
    <div className="shrink-0 border-b border-border bg-muted/20 px-3 py-2">
      <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_310px]">
        <div className="min-w-0">
          <div className="mb-1 flex items-center gap-2 text-[11px] text-muted-foreground">
            <span>Timeline density</span>
            <span className="ml-auto">{compactNumber(events.length)} loaded events</span>
          </div>
          {buckets.length === 0 ? (
            <div className="flex h-14 items-center justify-center rounded-md border border-border bg-card text-xs text-muted-foreground">
              No timestamped events to scrub.
            </div>
          ) : (
            <div className="flex h-14 items-end gap-px rounded-md border border-border bg-card p-1">
              {buckets.map((bucket) => (
                <button
                  key={bucket.date}
                  type="button"
                  onClick={() => onWindowChange(bucket.date, bucket.date)}
                  className="group flex min-w-1 flex-1 items-end"
                  title={`${bucket.date}: ${compactNumber(bucket.count)} events`}
                >
                  <span
                    className="block w-full rounded-t transition-opacity group-hover:opacity-70"
                    style={{
                      height: `${Math.max(4, (bucket.count / max) * 42)}px`,
                      background: dominantColor(bucket.byType),
                      opacity: isBucketActive(bucket.date, startDate, endDate) ? 1 : 0.36,
                    }}
                  />
                </button>
              ))}
            </div>
          )}
        </div>
        <div className="grid grid-cols-[1fr_1fr_auto] items-end gap-2">
          <label className="space-y-1">
            <span className="text-[11px] text-muted-foreground">From</span>
            <Input
              type="date"
              value={startDate}
              onChange={(event) => onWindowChange(event.target.value, endDate)}
              className="h-8 text-xs"
            />
          </label>
          <label className="space-y-1">
            <span className="text-[11px] text-muted-foreground">Until</span>
            <Input
              type="date"
              value={endDate}
              onChange={(event) => onWindowChange(startDate, event.target.value)}
              className="h-8 text-xs"
            />
          </label>
          <Button
            type="button"
            variant={hasWindow ? "secondary" : "outline"}
            size="sm"
            className="h-8 px-2"
            onClick={() => onWindowChange("", "")}
            title="Reset date window"
          >
            <RotateCcw className="size-3.5" />
          </Button>
        </div>
      </div>
    </div>
  )
}

type Bucket = {
  date: string
  count: number
  byType: Record<string, number>
}

function buildBuckets(events: TimelineItem[]): Bucket[] {
  const byDate = new Map<string, Bucket>()
  events.forEach((event) => {
    const date = parseTs(eventTimestamp(event))
    if (!date) return
    const day = toDateInput(date)
    const type = eventType(event)
    const bucket = byDate.get(day) ?? { date: day, count: 0, byType: {} }
    bucket.count += 1
    bucket.byType[type] = (bucket.byType[type] ?? 0) + 1
    byDate.set(day, bucket)
  })
  return [...byDate.values()].sort((a, b) => a.date.localeCompare(b.date)).slice(-96)
}

function dominantColor(byType: Record<string, number>): string {
  const [type] = Object.entries(byType).sort((a, b) => b[1] - a[1])[0] ?? ["event"]
  return eventColor(type)
}

function isBucketActive(date: string, startDate: string, endDate: string): boolean {
  if (!startDate && !endDate) return true
  if (startDate && date < startDate) return false
  if (endDate && date > endDate) return false
  return true
}

