import { render } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

import type { StreamItem, UseStream } from "../hooks/use-stream"
import { StreamList } from "./StreamList"

// The conversation list's page re-renders as each window of messages arrives, with a new stream object each time.
// Two pieces of the list used to read every row again on each of those renders: the selection report (with nothing
// selected) and the request for the windows around the visible rows.
const ROWS = 3000

function fakeStream(item: (i: number) => StreamItem, ensure: UseStream["ensure"], rowsVersion: number): UseStream {
  return {
    status: "ready",
    error: null,
    index: null,
    segments: [],
    count: ROWS,
    total: ROWS,
    notice: null,
    item,
    rowsVersion,
    ensure,
    retry: vi.fn(),
    reload: vi.fn(),
    positionOf: () => null,
    allRows: async () => [],
    checkSnapshot: async () => true,
    setFocused: vi.fn(),
  }
}

describe("StreamList on a page that re-renders", () => {
  it("reads no row again and asks for no window again until the rows or the visible range change", () => {
    const rows: StreamItem[] = Array.from({ length: ROWS }, (_, i) => ({
      type: "row",
      segment: 0,
      offset: i,
      row: null,
      state: "loading",
      windowKey: `0|${Math.floor(i / 200) * 200}`,
    }))
    const item = vi.fn((i: number) => rows[i])
    const ensure = vi.fn()
    const onSelectionChange = vi.fn()
    const list = (version: number) => (
      <StreamList
        stream={fakeStream(item, ensure, version)}
        caseId="c"
        caseName="Synthetic case"
        filterWords="none"
        zoneName="Eastern Time"
        zone="America/New_York"
        onSelectionChange={onSelectionChange}
      />
    )
    const view = render(list(1))
    const reads = item.mock.calls.length
    const asks = ensure.mock.calls.length
    expect(asks).toBe(1)

    for (let k = 0; k < 5; k++) view.rerender(list(1))
    expect(ensure.mock.calls.length).toBe(asks)
    // the virtual list itself reads a few visible items; never the whole list again
    expect(item.mock.calls.length - reads).toBeLessThan(ROWS)

    view.rerender(list(2)) // a window arrived: the rows around the view are asked for again
    expect(ensure.mock.calls.length).toBe(asks + 1)
    expect(onSelectionChange).toHaveBeenCalledTimes(1)
    expect(onSelectionChange).toHaveBeenCalledWith([], false)
  })
})
