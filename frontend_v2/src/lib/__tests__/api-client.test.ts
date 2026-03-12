import { describe, it, expect, vi, beforeEach, afterEach } from "vitest"
import { fetchAPI, ApiError } from "../api-client"

describe("fetchAPI", () => {
  const originalFetch = globalThis.fetch

  beforeEach(() => {
    globalThis.fetch = vi.fn()
    localStorage.clear()
  })

  afterEach(() => {
    globalThis.fetch = originalFetch
  })

  it("makes GET request and parses JSON", async () => {
    const mockResponse = { data: "test" }
    vi.mocked(globalThis.fetch).mockResolvedValue(
      new Response(JSON.stringify(mockResponse), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      })
    )

    const result = await fetchAPI<{ data: string }>("/api/test")
    expect(result).toEqual(mockResponse)
    expect(globalThis.fetch).toHaveBeenCalledWith(
      "/api/test",
      expect.objectContaining({
        credentials: "include",
      })
    )
  })

  it("includes auth token when present", async () => {
    localStorage.setItem("authToken", "my-token")
    vi.mocked(globalThis.fetch).mockResolvedValue(
      new Response(JSON.stringify({}), { status: 200 })
    )

    await fetchAPI("/api/test")
    const [, options] = vi.mocked(globalThis.fetch).mock.calls[0]
    expect((options?.headers as Record<string, string>)["Authorization"]).toBe(
      "Bearer my-token"
    )
  })

  it("sends POST with JSON body and Content-Type", async () => {
    vi.mocked(globalThis.fetch).mockResolvedValue(
      new Response(JSON.stringify({ ok: true }), { status: 200 })
    )

    await fetchAPI("/api/test", {
      method: "POST",
      body: { key: "value" },
    })

    const [, options] = vi.mocked(globalThis.fetch).mock.calls[0]
    expect(options?.method).toBe("POST")
    expect(options?.body).toBe(JSON.stringify({ key: "value" }))
    expect((options?.headers as Record<string, string>)["Content-Type"]).toBe(
      "application/json"
    )
  })

  it("throws ApiError on non-OK response", async () => {
    vi.mocked(globalThis.fetch).mockResolvedValue(
      new Response(JSON.stringify({ detail: "Not found" }), {
        status: 404,
        headers: { "Content-Type": "application/json" },
      })
    )

    try {
      await fetchAPI("/api/test")
      expect.unreachable("should have thrown")
    } catch (err) {
      expect(err).toBeInstanceOf(ApiError)
      expect((err as ApiError).status).toBe(404)
      expect((err as ApiError).message).toBe("Not found")
    }
  })

  it("returns undefined for 204 responses", async () => {
    vi.mocked(globalThis.fetch).mockResolvedValue(
      new Response(null, { status: 204 })
    )

    const result = await fetchAPI<void>("/api/test")
    expect(result).toBeUndefined()
  })

  it("removes authToken on 401", async () => {
    localStorage.setItem("authToken", "expired")
    vi.mocked(globalThis.fetch).mockResolvedValue(
      new Response(JSON.stringify({ detail: "Unauthorized" }), { status: 401 })
    )

    await expect(fetchAPI("/api/test")).rejects.toThrow()
    expect(localStorage.getItem("authToken")).toBeNull()
  })
})
