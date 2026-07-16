import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { fetchProtectedBlob, ProtectedFileError } from "./protected-file"

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

  it("preserves structured confirmation-required errors", async () => {
    const detail = {
      confirmation_required: true,
      artifact_id: "artifact-1",
      title: "Transactions",
      format: "csv",
    }
    vi.mocked(globalThis.fetch).mockResolvedValue(
      new Response(JSON.stringify({ detail }), {
        status: 428,
        headers: { "Content-Type": "application/json" },
      })
    )

    await expect(fetchProtectedBlob("/api/agent/artifacts/artifact-1/export?format=csv")).rejects.toMatchObject({
      name: "ProtectedFileError",
      status: 428,
      detail,
    } satisfies Partial<ProtectedFileError>)
  })
})
