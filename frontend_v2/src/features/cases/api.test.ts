import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { casesAPI } from "./api"

describe("casesAPI", () => {
  const originalFetch = globalThis.fetch

  beforeEach(() => {
    globalThis.fetch = vi.fn()
    localStorage.clear()
  })

  afterEach(() => {
    globalThis.fetch = originalFetch
  })

  it("uses the all_cases view mode for super-admin case listings", async () => {
    vi.mocked(globalThis.fetch).mockResolvedValue(
      new Response(JSON.stringify({ cases: [], total: 0 }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      })
    )

    await casesAPI.list("all_cases")

    expect(globalThis.fetch).toHaveBeenCalledWith(
      "/api/cases?view_mode=all_cases",
      expect.objectContaining({
        credentials: "include",
      })
    )
  })

  it("sends title, description, and status in a metadata update", async () => {
    vi.mocked(globalThis.fetch).mockResolvedValue(
      new Response(JSON.stringify({ id: "case-1" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      })
    )

    await casesAPI.update("case-1", {
      title: "Operation Beacon",
      description: null,
      status: "on_hold",
    })

    expect(globalThis.fetch).toHaveBeenCalledWith(
      "/api/cases/case-1",
      expect.objectContaining({
        method: "PATCH",
        body: JSON.stringify({
          title: "Operation Beacon",
          description: null,
          status: "on_hold",
        }),
      })
    )
  })
})
