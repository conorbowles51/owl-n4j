import { renderHook } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import type { StreamRow } from "../schemas"
import type { StreamItem, UseStream } from "../hooks/use-stream"
import { useTopRow } from "./use-top-row"

const row = (uid: string) => ({ type: "row", segment: 0, offset: 0, row: { event_uid: uid } as StreamRow, state: "loaded", windowKey: "0|0" }) as StreamItem
const header = { type: "header" } as StreamItem
const loading = { type: "row", segment: 0, offset: 0, row: null, state: "loading", windowKey: "0|0" } as StreamItem
const stream = (items: StreamItem[]): Pick<UseStream, "count" | "item"> => ({ count: items.length, item: (i) => items[i] })

describe("the first message in view (07 J-15)", () => {
  it("is reported once, not again when focus moves and the stream object changes (live, 5 Nov: it overwrote the focused row)", () => {
    const onTop = vi.fn()
    const items = [header, row("a"), row("b")]
    const view = renderHook(({ s, top }) => useTopRow(s, top, 1, onTop), { initialProps: { s: stream(items), top: 0 } })
    expect(onTop).toHaveBeenCalledTimes(1)
    expect(onTop.mock.calls[0][0].event_uid).toBe("a")
    view.rerender({ s: stream(items), top: 0 })
    expect(onTop).toHaveBeenCalledTimes(1)
    view.rerender({ s: stream(items), top: 2 })
    expect(onTop).toHaveBeenCalledTimes(2)
    expect(onTop.mock.calls[1][0].event_uid).toBe("b")
  })

  it("skips rows of a window not loaded yet", () => {
    const onTop = vi.fn()
    renderHook(() => useTopRow(stream([header, loading, loading]), 0, 1, onTop))
    expect(onTop).not.toHaveBeenCalled()
  })
})
