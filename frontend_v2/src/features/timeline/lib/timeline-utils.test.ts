import { describe, expect, it, vi } from "vitest"
import {
  compareTimelineEvents,
  formatEventTime,
  getEventTimestamp,
  groupEventsByDate,
  getDateRange,
  buildDensityHistogram,
  isValidDate,
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
  it.each(["25:00", "12:99", "12:15:99", "09:00 garbage"])(
    "keeps a valid event day when its clock time is invalid: %s",
    (time) => {
      const item = event({ time })
      expect(formatEventTime(item)).toBe("No time")
      expect(getEventTimestamp(item)).toBe(
        new Date("2024-01-01T00:00:00").getTime()
      )
      expect(() => getDateRange([item])).not.toThrow()
    }
  )

  it.each(["2024-02-30", "2023-02-29", "2024-13-01", "not a date", ""])(
    "rejects impossible calendar dates: %s",
    (date) => expect(isValidDate(date)).toBe(false)
  )

  it("ignores invalid dates in ranges and histograms without losing valid events", () => {
    const valid = event({ key: "valid" })
    const invalid = event({ key: "invalid", date: "not a date" })
    expect(getDateRange([invalid, valid])).toEqual(getDateRange([valid]))
    expect(getDateRange([invalid])).toEqual({ min: "", max: "" })
    expect(buildDensityHistogram([invalid], [invalid])).toEqual([])
    const histogram = buildDensityHistogram([invalid, valid], [invalid, valid])
    expect(
      histogram.reduce((total, bucket) => total + bucket.totalCount, 0)
    ).toBe(1)
    expect(
      histogram.reduce((total, bucket) => total + bucket.filteredCount, 0)
    ).toBe(1)
  })

  it("computes ranges for the full supported dataset without spreading function arguments", () => {
    expect(() =>
      getDateRange(Array.from({ length: 200000 }, () => event({})))
    ).not.toThrow()
  })

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

describe("compareTimelineEvents on a large Timeline", () => {
  const make = (index: number): TimelineEvent => ({
    key: `k${(index * 7919) % 5000}`,
    name: `Event ${index}`,
    type: "Transaction",
    date: index % 97 === 0 ? "2021-02-30" : `20${10 + (index % 12)}-0${1 + (index % 9)}-1${index % 10}`,
    time: index % 3 === 0 ? null : `1${index % 10}:${10 + (index % 50)}`,
    amount: null,
    summary: null,
    notes: null,
    connections: [],
  })

  it("orders exactly as comparing freshly parsed timestamps, and follows a changed date", () => {
    const events = Array.from({ length: 3000 }, (_, index) => make(index))
    const fresh = (a: TimelineEvent, b: TimelineEvent) => {
      const aTs = getEventTimestamp(a, true)
      const bTs = getEventTimestamp(b, true)
      if (!Number.isFinite(aTs)) return Number.isFinite(bTs) ? 1 : a.key.localeCompare(b.key)
      if (!Number.isFinite(bTs)) return -1
      return aTs - bTs || a.key.localeCompare(b.key)
    }
    expect([...events].sort(compareTimelineEvents).map((e) => e.key)).toEqual(
      [...events].sort(fresh).map((e) => e.key)
    )
    const moved = events[5]
    moved.date = "1999-01-01"
    expect([...events].sort(compareTimelineEvents)[0]).toBe(moved)
  })

  it("follows a change to an event's time alone", () => {
    const at = (key: string, time: string | null): TimelineEvent => ({ ...make(1), key, date: "2024-03-05", time })
    const first = at("a", "09:00")
    const second = at("b", "10:00")
    const third = at("c", null) // no time: after timed events of that day
    expect([third, second, first].sort(compareTimelineEvents)).toEqual([first, second, third])
    second.time = "08:30"
    expect([third, first, second].sort(compareTimelineEvents)).toEqual([second, first, third])
    third.time = "07:00"
    expect([first, second, third].sort(compareTimelineEvents)).toEqual([third, second, first])
    first.time = null
    expect([first, second, third].sort(compareTimelineEvents)).toEqual([third, second, first])
  })

  it("parses each event's date about once per sort, not once per comparison", () => {
    const events = Array.from({ length: 3000 }, (_, index) => make(index))
    const RealDate = Date
    let constructed = 0
    class CountingDate extends RealDate {
      constructor(...args: ConstructorParameters<typeof Date>) {
        super(...args)
        constructed += 1
      }
    }
    vi.stubGlobal("Date", CountingDate)
    try {
      ;[...events].sort(compareTimelineEvents)
      ;[...events].reverse().sort(compareTimelineEvents)
    } finally {
      vi.unstubAllGlobals()
    }
    expect(constructed).toBeLessThan(events.length * 3)
  })
})

describe("displayEventTime (03 section 15.6)", () => {
  it("shows a full instant as 12-hour time with its zone, keeps a bare HH:MM as entered, and says No time otherwise", async () => {
    const { displayEventTime } = await import("./timeline-utils")
    expect(displayEventTime({ date: "2023-03-14T19:07:12Z", time: null })).toEqual({ text: "7:07 PM UTC", title: "Tue, Mar 14, 2023, 7:07:12 PM UTC" })
    expect(displayEventTime({ date: "2023-03-14T15:07:12-04:00", time: null }).text).toBe("7:07 PM UTC")
    expect(displayEventTime({ date: "2023-03-14", time: "14:30" })).toEqual({ text: "14:30", title: "Time as entered" })
    expect(displayEventTime({ date: "2023-03-14", time: null })).toEqual({ text: "No time", title: null })
  })
})

import { getEventInstant } from "./timeline-utils"

describe("getEventInstant (the window's anchor)", () => {
  it("returns an instant only when the event carries its offset, never a bare time of day", () => {
    expect(getEventInstant({ date: "2023-11-08T14:30:00-05:00", time: null })).toBe("2023-11-08T19:30:00.000Z")
    expect(getEventInstant({ date: "2023-11-08", time: "14:30:00Z" })).toBe("2023-11-08T14:30:00.000Z")
    expect(getEventInstant({ date: "2023-11-08", time: "14:30" })).toBeNull() // zone not known: never guessed
    expect(getEventInstant({ date: "2023-11-08", time: null })).toBeNull()
    expect(getEventInstant({ date: "2023-11-08T14:30:00", time: null })).toBeNull()
  })
})

import { toWindowEvent } from "./timeline-utils"

describe("toWindowEvent (the window's view of a Timeline event)", () => {
  it("treats a ledger row as a payment whether it is read from the ledger or projected from it", () => {
    const projected = { key: "k1", name: "Transfer To Wren Pennywhistle", type: "FinancialTransaction", date: "2023-11-08", time: null,
      amount: "390.02", summary: null, notes: null } as unknown as TimelineEvent
    expect(toWindowEvent(projected)).toEqual({ key: "k1", name: "Transfer To Wren Pennywhistle", type: "FinancialTransaction",
      at: null, date: "2023-11-08", payment: true })
    const ledger = { ...projected, key: "k2", type: "Payment", source: { kind: "transaction", id: "t", date_basis: "transaction", label: "", state: "current" } } as TimelineEvent
    expect(toWindowEvent(ledger).payment).toBe(true)
    const meeting = { ...projected, key: "k3", type: "Meeting", date: "2023-11-08T14:30:00Z" } as TimelineEvent
    expect(toWindowEvent(meeting)).toMatchObject({ at: "2023-11-08T14:30:00.000Z", payment: false })
  })
})
