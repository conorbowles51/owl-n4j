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

  it("keeps this sign-in by storing the token the change returns", async () => {
    // Changing the password ends every sign-in issued before it, this one's included.
    localStorage.setItem("authToken", "before-the-change")
    vi.mocked(globalThis.fetch).mockResolvedValue(
      new Response(JSON.stringify({ success: true, access_token: "after-the-change" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      })
    )
    await authAPI.changePassword("old-secret", "new-secret")
    expect(localStorage.getItem("authToken")).toBe("after-the-change")
  })
})
