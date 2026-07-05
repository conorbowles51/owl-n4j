import type { TimelineEvent } from "../api"
import type { EntityType } from "@/lib/theme"

/** Returns true if the string parses to a valid Date */
export function isValidDate(dateStr: string | null | undefined): boolean {
  if (!dateStr) return false
  const dateKey = normaliseDateKey(dateStr)
  const ts = new Date(`${dateKey}T00:00:00`).getTime()
  return !Number.isNaN(ts)
}

function normaliseDateKey(dateStr: string): string {
  return dateStr.includes("T") ? dateStr.split("T")[0] : dateStr.slice(0, 10)
}

function normaliseTimeValue(timeStr: string | null | undefined): string | null {
  if (!timeStr) return null
  const match = String(timeStr).match(/^(\d{2}:\d{2})/)
  return match ? match[1] : null
}

function getEmbeddedIsoTime(dateStr: string | null | undefined): string | null {
  if (!dateStr?.includes("T")) return null
  return normaliseTimeValue(dateStr.split("T")[1])
}

export function getEventDateKey(event: Pick<TimelineEvent, "date">): string {
  return normaliseDateKey(event.date)
}

export function getEventTimeValue(
  event: Pick<TimelineEvent, "date" | "time">
): string | null {
  return normaliseTimeValue(event.time) ?? getEmbeddedIsoTime(event.date)
}

export function formatEventTime(
  event: Pick<TimelineEvent, "date" | "time">
): string {
  return getEventTimeValue(event) ?? "No time"
}

export function getEventTimestamp(
  event: TimelineEvent,
  unknownTimeAtEnd = false
): number {
  const date = getEventDateKey(event)
  if (!date) return Number.NaN
  const time =
    getEventTimeValue(event) || (unknownTimeAtEnd ? "23:59:59" : "00:00:00")
  const normalizedTime = time.length === 5 ? `${time}:00` : time
  return new Date(`${date}T${normalizedTime}`).getTime()
}

export function compareTimelineEvents(
  a: TimelineEvent,
  b: TimelineEvent
): number {
  const delta = getEventTimestamp(a, true) - getEventTimestamp(b, true)
  if (delta !== 0) return delta
  return a.key.localeCompare(b.key)
}

export interface DateRange {
  min: string
  max: string
}

export interface DerivedEntity {
  key: string
  name: string
  type: EntityType
  eventCount: number
}

export interface TimelineCluster {
  startDate: string
  endDate: string
  eventCount: number
  label: string
}

/** Get date range from events with 5% padding on each side */
export function getDateRange(events: TimelineEvent[]): DateRange {
  if (events.length === 0) return { min: "", max: "" }

  const timestamps = events.map((e) => getEventTimestamp(e))
  const minTs = Math.min(...timestamps)
  const maxTs = Math.max(...timestamps)
  const span = maxTs - minTs || 86400000 // at least 1 day
  const padding = span * 0.05

  return {
    min: new Date(minTs - padding).toISOString().split("T")[0],
    max: new Date(maxTs + padding).toISOString().split("T")[0],
  }
}

/** Derive unique entities from event connections, grouped by type */
export function deriveEntities(events: TimelineEvent[]): DerivedEntity[] {
  const map = new Map<string, DerivedEntity>()

  for (const event of events) {
    for (const conn of event.connections) {
      const existing = map.get(conn.key)
      if (existing) {
        existing.eventCount++
      } else {
        map.set(conn.key, {
          key: conn.key,
          name: conn.name,
          type: conn.type.toLowerCase() as EntityType,
          eventCount: 1,
        })
      }
    }
  }

  return Array.from(map.values()).sort((a, b) => b.eventCount - a.eventCount)
}

// ---------------------------------------------------------------------------
// Cluster detection
// ---------------------------------------------------------------------------

const DAY_MS = 86400000

/** Calculate auto gap threshold: median inter-event interval x3, clamped to [30d, 365d] */
function autoGapThreshold(events: TimelineEvent[]): number {
  if (events.length < 2) return 90 * DAY_MS

  const sorted = events
    .map((e) => getEventTimestamp(e, true))
    .sort((a, b) => a - b)

  const intervals: number[] = []
  for (let i = 1; i < sorted.length; i++) {
    const gap = sorted[i] - sorted[i - 1]
    if (gap > 0) intervals.push(gap)
  }

  if (intervals.length === 0) return 90 * DAY_MS

  intervals.sort((a, b) => a - b)
  const median = intervals[Math.floor(intervals.length / 2)]
  return Math.max(30 * DAY_MS, Math.min(365 * DAY_MS, median * 3))
}

/** Detect clusters of events separated by gaps */
export function detectClusters(
  events: TimelineEvent[],
  minGapMs?: number
): TimelineCluster[] {
  if (events.length === 0) return []

  const threshold = minGapMs ?? autoGapThreshold(events)
  const sorted = [...events].sort(compareTimelineEvents)

  const clusters: TimelineCluster[] = []
  let clusterStartDate = getEventDateKey(sorted[0])
  let clusterEndDate = getEventDateKey(sorted[0])
  let previousEvent = sorted[0]
  let count = 1

  for (let i = 1; i < sorted.length; i++) {
    const event = sorted[i]
    const gap =
      getEventTimestamp(event, true) - getEventTimestamp(previousEvent, true)
    if (gap > threshold) {
      clusters.push({
        startDate: clusterStartDate,
        endDate: clusterEndDate,
        eventCount: count,
        label: formatClusterLabel(clusterStartDate, clusterEndDate, count),
      })
      clusterStartDate = getEventDateKey(event)
      clusterEndDate = getEventDateKey(event)
      count = 1
    } else {
      clusterEndDate = getEventDateKey(event)
      count++
    }
    previousEvent = event
  }

  clusters.push({
    startDate: clusterStartDate,
    endDate: clusterEndDate,
    eventCount: count,
    label: formatClusterLabel(clusterStartDate, clusterEndDate, count),
  })

  return clusters
}

function formatClusterLabel(start: string, end: string, count: number): string {
  const s = parseDateKey(start)
  const e = parseDateKey(end)
  const startStr = s.toLocaleDateString("en-US", {
    month: "short",
    year: "2-digit",
  })
  const endStr = e.toLocaleDateString("en-US", {
    month: "short",
    year: "2-digit",
  })
  if (startStr === endStr) return `${startStr} (${count})`
  return `${startStr} - ${endStr} (${count})`
}

// ---------------------------------------------------------------------------
// Date grouping for vertical event stream
// ---------------------------------------------------------------------------

export interface DateGroup {
  date: string
  label: string
  events: TimelineEvent[]
}

/** Parse a calendar-day key without applying UTC timezone offsets. */
function parseDateKey(dateStr: string): Date {
  const dateKey = normaliseDateKey(dateStr)
  const [year, month, day] = dateKey.split("-").map(Number)
  if (!year || !month || !day) return new Date(dateStr)
  return new Date(year, month - 1, day)
}

function formatDateHeader(dateStr: string): string {
  return parseDateKey(dateStr).toLocaleDateString("en-US", {
    weekday: "short",
    month: "short",
    day: "numeric",
    year: "numeric",
  })
}

/** Group sorted events by calendar day. */
export function groupEventsByDate(events: TimelineEvent[]): DateGroup[] {
  if (events.length === 0) return []

  const sorted = [...events].sort(compareTimelineEvents)

  const groups: DateGroup[] = []
  let currentKey = ""
  let currentGroup: DateGroup | null = null

  for (const event of sorted) {
    const groupKey = getEventDateKey(event)

    if (groupKey !== currentKey) {
      if (currentGroup) groups.push(currentGroup)
      currentKey = groupKey
      currentGroup = {
        date: groupKey,
        label: formatDateHeader(groupKey),
        events: [event],
      }
    } else {
      currentGroup!.events.push(event)
    }
  }
  if (currentGroup) groups.push(currentGroup)

  return groups
}

// ---------------------------------------------------------------------------
// Density histogram for overview bar
// ---------------------------------------------------------------------------

export interface DensityBucket {
  startDate: string
  endDate: string
  totalCount: number
  filteredCount: number
}

/** Build a density histogram with `bucketCount` buckets across the date range */
export function buildDensityHistogram(
  allEvents: TimelineEvent[],
  filteredEvents: TimelineEvent[],
  bucketCount = 100
): DensityBucket[] {
  if (allEvents.length === 0) return []

  const range = getDateRange(allEvents)
  const minTs = new Date(range.min).getTime()
  const maxTs = new Date(range.max).getTime()
  const span = maxTs - minTs || DAY_MS
  const bucketWidth = span / bucketCount

  const buckets: DensityBucket[] = Array.from(
    { length: bucketCount },
    (_, i) => ({
      startDate: new Date(minTs + i * bucketWidth).toISOString(),
      endDate: new Date(minTs + (i + 1) * bucketWidth).toISOString(),
      totalCount: 0,
      filteredCount: 0,
    })
  )

  for (const event of allEvents) {
    const ts = getEventTimestamp(event, true)
    const idx = Math.min(
      Math.floor((ts - minTs) / bucketWidth),
      bucketCount - 1
    )
    if (idx >= 0) buckets[idx].totalCount++
  }

  const filteredSet = new Set(filteredEvents.map((e) => e.key))
  for (const event of allEvents) {
    if (!filteredSet.has(event.key)) continue
    const ts = getEventTimestamp(event, true)
    const idx = Math.min(
      Math.floor((ts - minTs) / bucketWidth),
      bucketCount - 1
    )
    if (idx >= 0) buckets[idx].filteredCount++
  }

  return buckets
}
