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
    vi.mocked(globalThis.fetch).mockResolvedValue(
      new Response(null, { status: 404 })
    )

    await expect(
      fetchProtectedBlob("/api/evidence/missing/file")
    ).rejects.toThrow("File request failed: 404")
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

describe("protected source response ownership", () => {
  beforeEach(() => {
    localStorage.setItem("authToken", "first-user")
    vi.stubGlobal("fetch", vi.fn())
    vi.spyOn(URL, "createObjectURL")
      .mockReturnValueOnce("blob:new-source")
      .mockReturnValueOnce("blob:stale-source")
    vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => {})
  })
  afterEach(() => {
    localStorage.removeItem("authToken")
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  it.each(["cancelled", "signed out"])(
    "does not deliver file bytes when a read finishes after it was %s",
    async (change) => {
      let finish!: (blob: Blob) => void
      const body = new Promise<Blob>((resolve) => {
        finish = resolve
      })
      vi.mocked(fetch).mockResolvedValue({
        ok: true,
        blob: () => body,
      } as Response)
      const controller = new AbortController()
      const pending = fetchProtectedBlob("/source", controller.signal)
      if (change === "cancelled") controller.abort()
      else localStorage.removeItem("authToken")
      finish(new Blob(["old private bytes"]))
      await expect(pending).rejects.toThrow()
    }
  )

  it("ignores an old page response after closing and reopening the same source", async () => {
    let finish!: (blob: Blob) => void
    const body = new Promise<Blob>((resolve) => {
      finish = resolve
    })
    vi.mocked(fetch)
      .mockResolvedValueOnce({ ok: true, blob: () => body } as Response)
      .mockResolvedValueOnce(new Response("current bytes"))
    const { result, rerender } = renderHook(
      ({ enabled }) => useProtectedObjectUrl("/source", enabled),
      { initialProps: { enabled: true } }
    )
    rerender({ enabled: false })
    rerender({ enabled: true })
    await waitFor(() =>
      expect(result.current.objectUrl).toBe("blob:new-source")
    )
    await act(async () => {
      finish(new Blob(["old bytes"]))
      await body
    })
    expect(result.current.objectUrl).toBe("blob:new-source")
    expect(URL.createObjectURL).toHaveBeenCalledTimes(1)
  })

  it("reloads the same source for a new signed-in session without exposing the earlier URL", async () => {
    vi.mocked(fetch).mockResolvedValue(new Response("first bytes"))
    const { result, rerender } = renderHook(() =>
      useProtectedObjectUrl("/source")
    )
    await waitFor(() =>
      expect(result.current.objectUrl).toBe("blob:new-source")
    )
    vi.mocked(fetch).mockResolvedValue(new Response("second bytes"))
    localStorage.setItem("authToken", "second-user")
    rerender()
    expect(result.current.objectUrl).toBeNull()
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(2))
    expect(vi.mocked(fetch).mock.calls[1][1]?.headers).toEqual({
      Authorization: "Bearer second-user",
    })
    expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:new-source")
  })
})
