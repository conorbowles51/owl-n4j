import { describe, expect, it } from "vitest"
import {
  compareTimelineEvents,
  formatEventTime,
  getEventTimestamp,
  groupEventsByDate,
} from "./timeline-utils"
import type { TimelineEvent } from "../api"

function event(partial: Partial<TimelineEvent>): TimelineEvent {
  return {
    key: partial.key ?? "event",
    name: "Event",
    type: "Event",
    date: partial.date ?? "2024-01-01",
    time: partial.time ?? null,
    amount: null,
    summary: null,
    notes: null,
    connections: [],
  }
}

describe("timeline date/time utilities", () => {
  it("sorts timed events before unknown-time events on the same day", () => {
    const events = [
      event({ key: "unknown", date: "2024-01-01", time: null }),
      event({ key: "morning", date: "2024-01-01", time: "09:00" }),
      event({ key: "afternoon", date: "2024-01-01", time: "14:30" }),
    ].sort(compareTimelineEvents)

    expect(events.map((item) => item.key)).toEqual([
      "morning",
      "afternoon",
      "unknown",
    ])
  })

  it("combines date and time into a stable timestamp", () => {
    expect(
      getEventTimestamp(event({ date: "2024-01-01", time: "12:15" }))
    ).toBe(new Date("2024-01-01T12:15:00").getTime())
  })

  it("sorts ISO datetime values by their embedded time", () => {
    const events = [
      event({ key: "unknown", date: "2024-01-01", time: null }),
      event({ key: "afternoon", date: "2024-01-01T14:30:00", time: null }),
      event({ key: "morning", date: "2024-01-01T09:00:00", time: null }),
    ].sort(compareTimelineEvents)

    expect(events.map((item) => item.key)).toEqual([
      "morning",
      "afternoon",
      "unknown",
    ])
  })

  it("always groups the event stream by calendar day", () => {
    const groups = groupEventsByDate([
      event({ key: "later", date: "2024-01-20", time: null }),
      event({ key: "earlier", date: "2024-01-01", time: null }),
    ])

    expect(groups.map((group) => group.date)).toEqual([
      "2024-01-01",
      "2024-01-20",
    ])
  })

  it("formats event times as HH:mm or No time", () => {
    expect(
      formatEventTime(event({ date: "2024-01-01", time: "19:47:30" }))
    ).toBe("19:47")
    expect(
      formatEventTime(event({ date: "2024-01-01T20:51:00", time: null }))
    ).toBe("20:51")
    expect(formatEventTime(event({ date: "2024-01-01", time: null }))).toBe(
      "No time"
    )
  })
})
