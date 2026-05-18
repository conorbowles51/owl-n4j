import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import type { PointerEvent as ReactPointerEvent } from "react"
import { RotateCcw } from "lucide-react"

import { Button } from "@/components/ui/button"
import { cn } from "@/lib/cn"

import type { TimelineItem } from "../../types"
import { compactNumber } from "../shared/cellebrite-format"
import { eventColor, eventTimestamp, eventType, parseTs } from "../events/eventUtils"

type BucketUnit = "hour" | "day" | "week"

type Bucket = {
  start: number
  end: number
  count: number
  byType: Record<string, number>
}

export function TimelineScrubber({
  items,
  windowStart,
  windowEnd,
  onWindowChange,
  onBarClick,
}: {
  items: TimelineItem[]
  windowStart: Date | null
  windowEnd: Date | null
  onWindowChange: (start: Date | null, end: Date | null) => void
  onBarClick: (bucketStart: Date, bucketEnd: Date) => void
}) {
  const { minTs, maxTs, buckets, bucketSizeMs, bucketUnit } = useMemo(() => buildBuckets(items), [items])
  const hasRange = minTs !== null && maxTs !== null && minTs < maxTs
  const safeMinTs = hasRange ? minTs : 0
  const safeMaxTs = hasRange ? maxTs : 1
  const propStart = windowStart ? windowStart.getTime() : safeMinTs
  const propEnd = windowEnd ? windowEnd.getTime() : safeMaxTs
  const [dragPreview, setDragPreview] = useState<{ start: number; end: number } | null>(null)
  const effectiveStart = dragPreview ? dragPreview.start : propStart
  const effectiveEnd = dragPreview ? dragPreview.end : propEnd
  const isFullWindow = effectiveStart <= safeMinTs && effectiveEnd >= safeMaxTs
  const containerRef = useRef<HTMLDivElement | null>(null)
  const [width, setWidth] = useState(0)
  const dragRef = useRef<"start" | "end" | "window" | null>(null)
  const dragOffsetRef = useRef(0)
  const totalSpan = safeMaxTs - safeMinTs
  const chartHeight = 64
  const tickHeight = 18
  const maxCount = useMemo(() => Math.max(...buckets.map((bucket) => bucket.count), 1), [buckets])
  const bucketWidth = width / Math.max(buckets.length, 1)
  const visualBarWidth = Math.max(1, bucketWidth - 1)
  const ticks = useMemo(() => buildTicks(safeMinTs, safeMaxTs, 5), [safeMaxTs, safeMinTs])

  const tsToX = useCallback((ts: number) => ((ts - safeMinTs) / totalSpan) * width, [safeMinTs, totalSpan, width])
  const xToTs = useCallback(
    (x: number) => Math.round(safeMinTs + (x / Math.max(width, 1)) * totalSpan),
    [safeMinTs, totalSpan, width]
  )
  const startX = tsToX(Math.max(safeMinTs, Math.min(safeMaxTs, effectiveStart)))
  const endX = tsToX(Math.max(safeMinTs, Math.min(safeMaxTs, effectiveEnd)))

  useEffect(() => {
    if (!hasRange) return
    const element = containerRef.current
    if (!element) return
    const resize = () => setWidth(element.clientWidth || 0)
    resize()
    const observer = new ResizeObserver(resize)
    observer.observe(element)
    return () => observer.disconnect()
  }, [hasRange])

  const onPointerMove = useCallback(
    (event: PointerEvent) => {
      const mode = dragRef.current
      if (!mode) return
      const rect = containerRef.current?.getBoundingClientRect()
      if (!rect) return
      const px = Math.max(0, Math.min(rect.width, event.clientX - rect.left))
      if (mode === "start") {
        const ts = xToTs(px)
        setDragPreview({ start: Math.max(safeMinTs, Math.min(ts, effectiveEnd - bucketSizeMs)), end: effectiveEnd })
        return
      }
      if (mode === "end") {
        const ts = xToTs(px)
        setDragPreview({ start: effectiveStart, end: Math.min(safeMaxTs, Math.max(ts, effectiveStart + bucketSizeMs)) })
        return
      }
      const windowWidth = Math.max(2, endX - startX)
      const newStartPx = Math.max(0, Math.min(rect.width - windowWidth, px - dragOffsetRef.current))
      setDragPreview({ start: xToTs(newStartPx), end: xToTs(newStartPx + windowWidth) })
    },
    [bucketSizeMs, effectiveEnd, effectiveStart, endX, safeMaxTs, safeMinTs, startX, xToTs]
  )

  const onPointerUp = useCallback(() => {
    if (!dragRef.current) return
    dragRef.current = null
    setDragPreview((preview) => {
      if (preview) onWindowChange(new Date(preview.start), new Date(preview.end))
      return null
    })
  }, [onWindowChange])

  useEffect(() => {
    if (!hasRange) return
    window.addEventListener("pointermove", onPointerMove)
    window.addEventListener("pointerup", onPointerUp)
    return () => {
      window.removeEventListener("pointermove", onPointerMove)
      window.removeEventListener("pointerup", onPointerUp)
    }
  }, [hasRange, onPointerMove, onPointerUp])

  const startDrag = (mode: "start" | "end" | "window") => (event: ReactPointerEvent<HTMLDivElement>) => {
    event.preventDefault()
    event.stopPropagation()
    dragRef.current = mode
    if (mode === "window") {
      const rect = containerRef.current?.getBoundingClientRect()
      if (rect) dragOffsetRef.current = event.clientX - rect.left - startX
    }
    event.currentTarget.setPointerCapture(event.pointerId)
  }

  if (!hasRange) {
    return (
      <div className="shrink-0 border-b border-border bg-muted/20 px-3 py-2">
        <div className="flex h-14 items-center justify-center rounded-md border border-border bg-card text-xs text-muted-foreground">
          No timestamped events to scrub.
        </div>
      </div>
    )
  }

  return (
    <div className="shrink-0 border-b border-border bg-muted/20 px-3 py-2">
      <div ref={containerRef} className="relative w-full select-none" style={{ height: chartHeight + tickHeight }}>
        <div className="absolute inset-x-0 top-0 rounded-md border border-border bg-card" style={{ height: chartHeight }} />
        <svg className="absolute inset-x-0 top-0" width={width || 0} height={chartHeight} style={{ overflow: "visible" }}>
          {buckets.map((bucket, index) => {
            const inWindow = bucket.start >= effectiveStart - 1 && bucket.end <= effectiveEnd + 1
            const baseX = index * bucketWidth
            const totalHeight = (bucket.count / maxCount) * (chartHeight - 6)
            let cursorY = chartHeight - 3
            return (
              <g
                key={`${bucket.start}-${index}`}
                opacity={inWindow ? 1 : 0.28}
                onClick={() => onBarClick(new Date(bucket.start), new Date(bucket.end))}
                className="cursor-pointer"
              >
                <title>
                  {formatBucketLabel(bucket.start, bucketUnit)} - {compactNumber(bucket.count)} events
                </title>
                <rect x={baseX} y={0} width={bucketWidth} height={chartHeight} fill="transparent" />
                {Object.entries(bucket.byType)
                  .sort((a, b) => b[1] - a[1])
                  .map(([type, count]) => {
                    const segmentHeight = (count / Math.max(bucket.count, 1)) * totalHeight
                    cursorY -= segmentHeight
                    return (
                      <rect
                        key={type}
                        x={baseX + (bucketWidth - visualBarWidth) / 2}
                        y={cursorY}
                        width={visualBarWidth}
                        height={Math.max(0.5, segmentHeight)}
                        fill={eventColor(type)}
                      />
                    )
                  })}
              </g>
            )
          })}
        </svg>
        <div className="pointer-events-none absolute top-0 bg-foreground/10" style={{ left: 0, width: startX, height: chartHeight }} />
        <div className="pointer-events-none absolute top-0 bg-foreground/10" style={{ left: endX, right: 0, height: chartHeight }} />
        <div
          onPointerDown={startDrag("window")}
          className="absolute top-0 cursor-grab border-x-2 border-amber-500/80 active:cursor-grabbing"
          style={{ left: startX, width: Math.max(2, endX - startX), height: chartHeight }}
        />
        <TimelineHandle side="start" x={startX} height={chartHeight} onPointerDown={startDrag("start")} />
        <TimelineHandle side="end" x={endX} height={chartHeight} onPointerDown={startDrag("end")} />
        <div
          className="absolute inset-x-0 flex justify-between text-[10px] tabular-nums text-muted-foreground"
          style={{ top: chartHeight + 2 }}
        >
          {ticks.map((tick) => (
            <span key={tick}>{formatTick(tick, bucketUnit)}</span>
          ))}
        </div>
      </div>
      <div className="mt-1 flex items-center justify-between text-[11px] text-muted-foreground">
        <span>
          {isFullWindow ? (
            <>All time - {compactNumber(items.length)} loaded events</>
          ) : (
            <>
              <span className="font-medium text-foreground">{formatTick(effectiveStart, bucketUnit)}</span>
              <span className="mx-1.5">to</span>
              <span className="font-medium text-foreground">{formatTick(effectiveEnd, bucketUnit)}</span>
            </>
          )}
        </span>
        <Button
          type="button"
          variant={isFullWindow ? "ghost" : "outline"}
          size="sm"
          className={cn("h-7 px-2 text-xs", isFullWindow && "invisible")}
          onClick={() => onWindowChange(null, null)}
        >
          <RotateCcw className="mr-1 size-3" />
          Reset
        </Button>
      </div>
    </div>
  )
}

function TimelineHandle({
  side,
  x,
  height,
  onPointerDown,
}: {
  side: "start" | "end"
  x: number
  height: number
  onPointerDown: (event: ReactPointerEvent<HTMLDivElement>) => void
}) {
  return (
    <div onPointerDown={onPointerDown} className="absolute top-0 -translate-x-1/2 cursor-ew-resize" style={{ left: x, height }}>
      <div className={cn("h-full w-2.5 border border-amber-600 bg-amber-500 shadow", side === "start" ? "rounded-l" : "rounded-r")} />
    </div>
  )
}

function buildBuckets(items: TimelineItem[]): {
  minTs: number | null
  maxTs: number | null
  buckets: Bucket[]
  bucketSizeMs: number
  bucketUnit: BucketUnit
} {
  let minTs = Infinity
  let maxTs = -Infinity
  items.forEach((item) => {
    const timestamp = parseTs(eventTimestamp(item))?.getTime()
    if (!timestamp) return
    minTs = Math.min(minTs, timestamp)
    maxTs = Math.max(maxTs, timestamp)
  })
  if (!Number.isFinite(minTs) || !Number.isFinite(maxTs) || minTs === maxTs) {
    return { minTs: null, maxTs: null, buckets: [], bucketSizeMs: 0, bucketUnit: "day" }
  }

  const span = maxTs - minTs
  const pad = Math.max(span * 0.01, 1000)
  const unit = pickBucketUnit(span)
  const bucketSizeMs = unitMs(unit)
  const startBucket = floorTo(minTs - pad, unit)
  const bucketCount = Math.max(1, Math.ceil((maxTs + pad - startBucket) / bucketSizeMs))
  const buckets = Array.from({ length: bucketCount }, (_, index) => ({
    start: startBucket + index * bucketSizeMs,
    end: startBucket + (index + 1) * bucketSizeMs,
    count: 0,
    byType: {} as Record<string, number>,
  }))

  items.forEach((item) => {
    const timestamp = parseTs(eventTimestamp(item))?.getTime()
    if (!timestamp) return
    const index = Math.min(bucketCount - 1, Math.max(0, Math.floor((timestamp - startBucket) / bucketSizeMs)))
    const bucket = buckets[index]
    const type = eventType(item)
    bucket.count += 1
    bucket.byType[type] = (bucket.byType[type] ?? 0) + 1
  })

  return {
    minTs: startBucket,
    maxTs: startBucket + bucketCount * bucketSizeMs,
    buckets,
    bucketSizeMs,
    bucketUnit: unit,
  }
}

function pickBucketUnit(spanMs: number): BucketUnit {
  const days = spanMs / (24 * 60 * 60 * 1000)
  if (days <= 2) return "hour"
  if (days <= 120) return "day"
  return "week"
}

function unitMs(unit: BucketUnit): number {
  if (unit === "hour") return 60 * 60 * 1000
  if (unit === "week") return 7 * 24 * 60 * 60 * 1000
  return 24 * 60 * 60 * 1000
}

function floorTo(timestamp: number, unit: BucketUnit): number {
  const date = new Date(timestamp)
  if (unit === "hour") {
    date.setMinutes(0, 0, 0)
    return date.getTime()
  }
  if (unit === "week") {
    date.setHours(0, 0, 0, 0)
    date.setDate(date.getDate() - ((date.getDay() + 6) % 7))
    return date.getTime()
  }
  date.setHours(0, 0, 0, 0)
  return date.getTime()
}

function buildTicks(minTs: number, maxTs: number, count: number): number[] {
  return Array.from({ length: count }, (_, index) => minTs + ((maxTs - minTs) * index) / (count - 1))
}

function formatTick(timestamp: number, unit: BucketUnit): string {
  const date = new Date(timestamp)
  if (unit === "hour") {
    return date.toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })
  }
  return date.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" })
}

function formatBucketLabel(timestamp: number, unit: BucketUnit): string {
  const date = new Date(timestamp)
  if (unit === "hour") {
    return date.toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })
  }
  if (unit === "week") {
    const end = new Date(timestamp + 6 * 24 * 60 * 60 * 1000)
    return `${date.toLocaleDateString(undefined, { month: "short", day: "numeric" })} to ${end.toLocaleDateString(undefined, {
      month: "short",
      day: "numeric",
    })}`
  }
  return date.toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" })
}
