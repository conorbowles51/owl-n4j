import { act, renderHook, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { fetchProtectedBlob, useProtectedObjectUrl } from "./protected-file"

describe("fetchProtectedBlob", () => {
  const originalFetch = globalThis.fetch

  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn())
    const storage = new Map<string, string>()
    vi.stubGlobal("localStorage", {
      getItem: vi.fn((key: string) => storage.get(key) ?? null),
      setItem: vi.fn((key: string, value: string) => storage.set(key, value)),
      removeItem: vi.fn((key: string) => storage.delete(key)),
      clear: vi.fn(() => storage.clear()),
    })
  })

  afterEach(() => {
    globalThis.fetch = originalFetch
    vi.unstubAllGlobals()
  })

  it("fetches protected file bytes with bearer auth and cookies", async () => {
    localStorage.setItem("authToken", "file-token")
    vi.mocked(globalThis.fetch).mockResolvedValue(
      new Response("image", {
        status: 200,
        headers: { "Content-Type": "image/png" },
      })
    )

    const blob = await fetchProtectedBlob("/api/evidence/123/file")

    expect(blob.type).toBe("image/png")
    expect(globalThis.fetch).toHaveBeenCalledWith(
      "/api/evidence/123/file",
      expect.objectContaining({
        credentials: "include",
        headers: { Authorization: "Bearer file-token" },
      })
    )
  })

  it("throws when the protected file request fails", async () => {
    vi.mocked(globalThis.fetch).mockResolvedValue(new Response(null, { status: 404 }))

    await expect(fetchProtectedBlob("/api/evidence/missing/file")).rejects.toThrow(
      "File request failed: 404"
    )
  })
})

describe("useProtectedObjectUrl", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn())
    vi.stubGlobal("URL", {
      createObjectURL: vi
        .fn()
        .mockReturnValueOnce("blob:protected-first")
        .mockReturnValueOnce("blob:protected-second"),
      revokeObjectURL: vi.fn(),
    })
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it("does not expose a revoked object URL while reopening the same file", async () => {
    let resolveFirst!: (response: Response) => void
    let resolveSecond!: (response: Response) => void
    const firstRequest = new Promise<Response>((resolve) => {
      resolveFirst = resolve
    })
    const secondRequest = new Promise<Response>((resolve) => {
      resolveSecond = resolve
    })
    vi.mocked(globalThis.fetch)
      .mockReturnValueOnce(firstRequest)
      .mockReturnValueOnce(secondRequest)

    const { result, rerender } = renderHook(
      ({ enabled }) =>
        useProtectedObjectUrl("/api/evidence/audio-1/file", enabled),
      { initialProps: { enabled: true } }
    )

    await act(async () => {
      resolveFirst(new Response("first audio"))
      await firstRequest
    })
    await waitFor(() =>
      expect(result.current.objectUrl).toBe("blob:protected-first")
    )

    rerender({ enabled: false })
    expect(result.current.objectUrl).toBeNull()
    expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:protected-first")

    rerender({ enabled: true })
    expect(result.current.objectUrl).toBeNull()
    expect(result.current.loading).toBe(true)

    await act(async () => {
      resolveSecond(new Response("second audio"))
      await secondRequest
    })
    await waitFor(() =>
      expect(result.current.objectUrl).toBe("blob:protected-second")
    )
  })
})
