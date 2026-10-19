import { afterEach, beforeEach, expect, it, vi } from "vitest"
import { fetchAPI } from "./api-client"
beforeEach(() => localStorage.clear())
afterEach(() => vi.unstubAllGlobals())
it("does not clear a new login when a previous session's delayed request returns 401", async () => {
  localStorage.setItem("authToken", "old-session")
  let finish!: (value: Response) => void
  const fetch = vi.fn(
    () =>
      new Promise<Response>((resolve) => {
        finish = resolve
      })
  )
  vi.stubGlobal("fetch", fetch)
  const request = fetchAPI("/api/financial/ledger?case_id=old-case").catch(
    (error) => error
  )
  localStorage.setItem("authToken", "new-session")
  finish(new Response(JSON.stringify({ detail: "Expired" }), { status: 401 }))
  expect(await request).toMatchObject({ status: 401 })
  expect(localStorage.getItem("authToken")).toBe("new-session")
  expect(fetch).toHaveBeenCalledWith(
    "/api/financial/ledger?case_id=old-case",
    expect.objectContaining({
      headers: expect.objectContaining({ Authorization: "Bearer old-session" }),
    })
  )
})
it("removes the token when the current session expires", async () => {
  localStorage.setItem("authToken", "expired-session")
  vi.stubGlobal(
    "fetch",
    vi
      .fn()
      .mockResolvedValue(
        new Response(JSON.stringify({ detail: "Expired" }), { status: 401 })
      )
  )
  await expect(
    fetchAPI("/api/financial/case-access?case_id=case")
  ).rejects.toMatchObject({ status: 401 })
  expect(localStorage.getItem("authToken")).toBeNull()
})
