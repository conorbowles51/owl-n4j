import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { casesAPI } from "./api"

describe("casesAPI.list", () => {
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
})
