import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { significantAPI } from "./api"

describe("significantAPI", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn())
    vi.stubGlobal("localStorage", {
      getItem: vi.fn(() => null),
      removeItem: vi.fn(),
      setItem: vi.fn(),
    })
  })

  afterEach(() => vi.unstubAllGlobals())

  it("adds a deduplicated selection as manifest references", async () => {
    vi.mocked(globalThis.fetch).mockResolvedValue(
      new Response(
        JSON.stringify({
          case_id: "case-1",
          entity_keys: ["person-1", "event-2"],
          items: [],
          count: 2,
          added_count: 2,
        }),
        { status: 200, headers: { "Content-Type": "application/json" } }
      )
    )

    await significantAPI.addEntities(
      "case-1",
      ["person-1", "event-2", "person-1"],
      "selection",
      { surface: "table" }
    )

    const [url, options] = vi.mocked(globalThis.fetch).mock.calls[0]
    expect(url).toBe("/api/significant/case-1/entities:batch")
    expect(options?.method).toBe("POST")
    expect(JSON.parse(options?.body as string)).toEqual({
      entity_keys: ["person-1", "event-2", "person-1"],
      source: "selection",
      context: { surface: "table" },
    })
  })
})
