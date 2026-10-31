import { afterEach, beforeEach, expect, it, vi } from "vitest"
import { apiRequestsInFlight, fetchAPI } from "./api-client"
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
it("counts requests in flight until each finishes, failed or not", async () => {
  const finishes: ((value: Response) => void)[] = []
  vi.stubGlobal("fetch", vi.fn(() => new Promise<Response>((resolve) => { finishes.push(resolve) })))
  expect(apiRequestsInFlight()).toBe(0)
  const ok = fetchAPI("/api/a")
  const bad = fetchAPI("/api/b").catch((error) => error)
  expect(apiRequestsInFlight()).toBe(2)
  finishes[0](new Response("{}", { status: 200 }))
  await ok
  expect(apiRequestsInFlight()).toBe(1)
  finishes[1](new Response("{}", { status: 500 }))
  await bad
  expect(apiRequestsInFlight()).toBe(0)
})
