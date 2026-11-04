import { act, renderHook, waitFor } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

import type { StreamFilter } from "../api"
import type { StreamIndex, StreamWindow } from "../schemas"
import { useStream, type StreamSource, type UseStream } from "./use-stream"

// Consumers key their work over every row on the stream object (the badges' windows, the selection report, the
// list's window request). It is one object per state of the list, so a page render that changes nothing about the
// list does not make them run again; a window arriving does.
describe("useStream identity", () => {
  it("returns the same stream on a re-render that changes nothing, and a new one when rows arrive", async () => {
    const index = {
      snapshot: "s1",
      counts: { events: 2 },
      full_load_rows: 5000,
      items: [{ day: "2026-01-02", header: "Friday 2 January 2026", zone_label: "UTC", count: 2 }],
      no_time_count: 0,
      no_time_position: "last",
    } as unknown as StreamIndex
    let release: (w: StreamWindow) => void = () => {}
    const source: StreamSource = {
      index: vi.fn(async () => index),
      window: vi.fn(() => new Promise<StreamWindow>((resolve) => (release = resolve))),
      locate: vi.fn(),
    }
    const filter = { case_id: "c" } as unknown as StreamFilter
    const { result, rerender } = renderHook(({ tick }: { tick: number }) => {
      void tick
      return useStream(filter, { source })
    }, { initialProps: { tick: 0 } })
    await waitFor(() => expect(result.current.status).toBe("ready"))
    await waitFor(() => expect(source.window).toHaveBeenCalled())

    const before: UseStream = result.current
    rerender({ tick: 1 })
    rerender({ tick: 2 })
    expect(result.current).toBe(before)

    await act(async () => {
      release({ items: [{ event_uid: "e1" }, { event_uid: "e2" }] } as unknown as StreamWindow)
    })
    expect(result.current).not.toBe(before)
    expect(result.current.rowsVersion).not.toBe(before.rowsVersion)
  })
})
