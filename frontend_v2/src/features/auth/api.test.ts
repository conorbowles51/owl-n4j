import { describe, it, expect, vi, beforeEach, afterEach } from "vitest"
import { authAPI } from "./api"

describe("authAPI.changePassword", () => {
  const originalFetch = globalThis.fetch

  beforeEach(() => {
    globalThis.fetch = vi.fn()
    localStorage.clear()
  })

  afterEach(() => {
    globalThis.fetch = originalFetch
  })

  it("keeps this sign-in on the cookie the reply sets, and stores no token", async () => {
    // Changing the password ends every sign-in issued before it, this one's included.
    localStorage.setItem("loupeSession", "before-the-change")
    vi.mocked(globalThis.fetch).mockResolvedValue(
      new Response(JSON.stringify({ success: true, access_token: "after-the-change" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      })
    )
    await authAPI.changePassword("old-secret", "new-secret")
    expect(localStorage.getItem("loupeSession")).toBe("before-the-change")
    expect(JSON.stringify({ ...localStorage })).not.toContain("after-the-change")
  })
})
