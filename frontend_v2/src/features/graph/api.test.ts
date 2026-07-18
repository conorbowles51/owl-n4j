import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { graphAPI } from "./api"

describe("graphAPI edit helpers", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn())
    vi.stubGlobal("localStorage", {
      getItem: vi.fn(() => null),
      removeItem: vi.fn(),
      setItem: vi.fn(),
    })
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it("sends case-scoped node edit payloads", async () => {
    vi.mocked(globalThis.fetch).mockResolvedValue(
      new Response(JSON.stringify({ success: true, updated_fields: [], changes: {} }), {
        status: 200,
      })
    )

    await graphAPI.updateNode("event-1", {
      case_id: "case-1",
      category: "Communication",
      properties: { date: "2024-01-02", time: "14:30" },
      source_view: "timeline",
    })

    const [url, options] = vi.mocked(globalThis.fetch).mock.calls[0]
    expect(url).toBe("/api/graph/node/event-1")
    expect(options?.method).toBe("PUT")
    expect(JSON.parse(options?.body as string)).toEqual({
      case_id: "case-1",
      category: "Communication",
      properties: { date: "2024-01-02", time: "14:30" },
      source_view: "timeline",
    })
  })

  it("supports geocode preview without applying immediately", async () => {
    vi.mocked(globalThis.fetch).mockResolvedValue(
      new Response(
        JSON.stringify({
          success: true,
          latitude: 51.5,
          longitude: -0.12,
          formatted_address: "London, UK",
          confidence: "high",
          applied: false,
        }),
        { status: 200 }
      )
    )

    await graphAPI.geocodeNode("loc-1", "case-1", "London", false, "map_popup")

    const [url, options] = vi.mocked(globalThis.fetch).mock.calls[0]
    expect(url).toBe("/api/graph/node/loc-1/geocode?apply=false")
    expect(options?.method).toBe("POST")
    expect(JSON.parse(options?.body as string)).toEqual({
      case_id: "case-1",
      address: "London",
      source_view: "map_popup",
    })
  })

  it("supports undoing the last location correction", async () => {
    vi.mocked(globalThis.fetch).mockResolvedValue(
      new Response(
        JSON.stringify({
          success: true,
          latitude: 40.7,
          longitude: -74,
          formatted_address: "New York, NY",
          confidence: "low",
        }),
        { status: 200 }
      )
    )

    await graphAPI.undoLocationCorrection("loc-1", "case-1", "evidence_panel")

    const [url, options] = vi.mocked(globalThis.fetch).mock.calls[0]
    expect(url).toBe("/api/graph/node/loc-1/geocode/undo")
    expect(options?.method).toBe("POST")
    expect(JSON.parse(options?.body as string)).toEqual({
      case_id: "case-1",
      source_view: "evidence_panel",
    })
  })
})
