import { renderHook } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { useCsvExport } from "./use-csv-export"
import type { GraphNode } from "@/types/graph.types"

describe("useCsvExport", () => {
  let clickSpy: ReturnType<typeof vi.spyOn>

  beforeEach(() => {
    Object.defineProperty(URL, "createObjectURL", {
      configurable: true,
      value: vi.fn(() => "blob:test"),
    })
    Object.defineProperty(URL, "revokeObjectURL", {
      configurable: true,
      value: vi.fn(),
    })
    clickSpy = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {})
  })

  afterEach(() => {
    clickSpy.mockRestore()
    vi.restoreAllMocks()
  })

  it("always includes manual provenance columns", async () => {
    const node: GraphNode = {
      key: "node-1",
      label: "Manual assertion",
      type: "person",
      properties: {
        user_created: true,
        created_by: "analyst@example.com",
        created_at: "2026-07-17T12:00:00+00:00",
        source: "manual",
      },
    }
    const { result } = renderHook(() => useCsvExport())

    result.current.exportCSV({
      nodes: [node],
      columns: [
        {
          key: "_checkbox",
          label: "",
          fixed: true,
          sortable: false,
          defaultVisible: true,
        },
        {
          key: "label",
          label: "Name",
          fixed: true,
          sortable: true,
          defaultVisible: true,
        },
      ],
      connectionCounts: new Map(),
      sourceCounts: new Map(),
      filename: "case.csv",
    })

    const blob = vi.mocked(URL.createObjectURL).mock.calls[0][0] as Blob
    const csv = await blob.text()

    expect(csv).toContain("Name,User Created,Created By,Created At,Source")
    expect(csv).toContain(
      "Manual assertion,true,analyst@example.com,2026-07-17T12:00:00+00:00,manual"
    )
    expect(clickSpy).toHaveBeenCalled()
  })
})
