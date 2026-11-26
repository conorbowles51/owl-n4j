import { renderHook, waitFor } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

import type { StreamFilter } from "../api"
import type { StreamIndex, StreamWindow } from "../schemas"
import { useStream, type StreamSource } from "./use-stream"

// followups 26 Nov: a short lens result loaded one request per day (113 requests for 275 entries on the Corwen Street
// case). The full load asks for runs of whole days, up to 1,000 rows a request, and splits them by the index's counts.
const DAYS = [["2026-01-02", 2], ["2026-01-03", 1], ["2026-01-05", 1]] as const
const index = {
  snapshot: "s1",
  counts: { events: 5 },
  full_load_rows: 5000,
  items: DAYS.map(([day, count]) => ({ day, header: day, zone_label: "UTC", count })),
  no_time_count: 1,
  no_time_position: "last",
} as unknown as StreamIndex
const rowsOf = (day: string | null, n: number) => Array.from({ length: n }, (_, k) => ({ event_uid: `${day}:${k}` }))
const filter = { case_id: "c" } as unknown as StreamFilter

function source(spanCount?: number): StreamSource {
  return {
    index: vi.fn(async () => index),
    window: vi.fn(async (_f, _s, day: string | null) => ({
      items: rowsOf(day, day ? DAYS.find((d) => d[0] === day)![1] : 1),
    }) as unknown as StreamWindow),
    locate: vi.fn(),
    span: vi.fn(async () => ({
      items: DAYS.flatMap(([d, n]) => rowsOf(d, n)).slice(0, spanCount ?? 4),
    }) as unknown as StreamWindow),
  }
}

function listed(result: { current: ReturnType<typeof useStream> }): string[] {
  const out: string[] = []
  for (let i = 0; i < result.current.count; i++) {
    const it = result.current.item(i)
    if (it.type === "row") out.push(it.row ? (it.row as unknown as { event_uid: string }).event_uid : "missing")
  }
  return out
}

const WANT = ["2026-01-02:0", "2026-01-02:1", "2026-01-03:0", "2026-01-05:0", "null:0"]

describe("useStream full load in runs of days", () => {
  it("asks once for the dated days and once for the no-time group, same rows and order", async () => {
    const src = source()
    const { result } = renderHook(() => useStream(filter, { source: src }))
    await waitFor(() => expect(listed(result)).toEqual(WANT))
    expect(src.span).toHaveBeenCalledTimes(1)
    expect(src.span).toHaveBeenCalledWith(filter, "s1", "2026-01-02", "2026-01-05", 4)
    expect(src.window).toHaveBeenCalledTimes(1)
    expect((src.window as ReturnType<typeof vi.fn>).mock.calls[0][2]).toBeNull()
  })

  it("a run that does not add up to the index's counts is asked again one day at a time", async () => {
    const src = source(3)
    const { result } = renderHook(() => useStream(filter, { source: src }))
    await waitFor(() => expect(listed(result)).toEqual(WANT))
    expect(src.window).toHaveBeenCalledTimes(4)
  })
})
