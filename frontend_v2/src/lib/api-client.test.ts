import { afterEach, beforeEach, expect, it, vi } from "vitest"
import { ACCESS_REFUSED_EVENT } from "./access-refused"
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
it.each([
  [401, true],
  [403, true],
  [404, false],
  [500, false],
])(
  "announces a %s answer to permission holders: %s",
  async (status, announced) => {
    const heard: string[] = []
    const listen = (event: Event) =>
      heard.push((event as CustomEvent<string>).detail)
    window.addEventListener(ACCESS_REFUSED_EVENT, listen)
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response("{}", { status }))
    )
    await expect(
      fetchAPI("/api/financial/ledger?case_id=c")
    ).rejects.toMatchObject({ status })
    window.removeEventListener(ACCESS_REFUSED_EVENT, listen)
    expect(heard).toEqual(announced ? ["/api/financial/ledger?case_id=c"] : [])
  }
)
it("asks Financial reads to be answered as updating and records such answers until the address answers current", async () => {
  const { clearUpdatingViews, updatingViews } = await import("./financial-view-updates")
  clearUpdatingViews()
  const endpoint = "/api/financial/ledger-summary?case_id=c1"
  const fetch = vi
    .fn()
    .mockResolvedValueOnce(
      new Response('{"total":5}', {
        status: 200,
        headers: { "X-Financial-View-State": "updating", "X-Financial-View-As-Of": "2026-10-31T07:15:00+00:00" },
      })
    )
    .mockResolvedValueOnce(new Response('{"total":12}', { status: 200 }))
  vi.stubGlobal("fetch", fetch)
  expect(await fetchAPI(endpoint)).toEqual({ total: 5 })
  expect(fetch.mock.calls[0][1].headers["X-Financial-View-Accept"]).toBe("updating")
  expect(updatingViews().get(endpoint)).toBe("2026-10-31T07:15:00+00:00")
  expect(await fetchAPI(endpoint)).toEqual({ total: 12 })
  expect(updatingViews().has(endpoint)).toBe(false)
})
it("records a kept refusal answered as updating, and never asks writes or other reads to accept it", async () => {
  const { clearUpdatingViews, updatingViews } = await import("./financial-view-updates")
  clearUpdatingViews()
  const endpoint = "/api/financial/ledger-timeline?case_id=c1"
  const fetch = vi.fn().mockImplementation(() =>
    Promise.resolve(
      new Response('{"detail":"More than 1,000 payments match."}', {
        status: 422,
        headers: { "X-Financial-View-State": "updating", "X-Financial-View-As-Of": "2026-10-31T07:15:00+00:00" },
      })
    )
  )
  vi.stubGlobal("fetch", fetch)
  await expect(fetchAPI(endpoint)).rejects.toMatchObject({ status: 422 })
  expect(updatingViews().has(endpoint)).toBe(true)
  await fetchAPI("/api/financial/ledger/categories?case_id=c1", { method: "POST", body: {} }).catch(() => undefined)
  await fetchAPI("/api/evidence?case_id=c1").catch(() => undefined)
  expect(fetch.mock.calls[1][1].headers["X-Financial-View-Accept"]).toBeUndefined()
  expect(fetch.mock.calls[2][1].headers["X-Financial-View-Accept"]).toBeUndefined()
  expect([...updatingViews().keys()]).toEqual([endpoint])
})
it("never asks to be answered as updating for two minutes after this tab saves something", async () => {
  const { AFTER_OWN_WRITE_MS, clearUpdatingViews } = await import("./financial-view-updates")
  clearUpdatingViews()
  vi.useFakeTimers()
  try {
    const fetch = vi.fn().mockImplementation(() => Promise.resolve(new Response("{}", { status: 200 })))
    vi.stubGlobal("fetch", fetch)
    await fetchAPI("/api/financial/counterparty-parties/links?case_id=c1", { method: "POST", body: {} })
    await fetchAPI("/api/financial/counterparty-parties?case_id=c1")
    expect(fetch.mock.calls[1][1].headers["X-Financial-View-Accept"]).toBeUndefined()
    vi.advanceTimersByTime(AFTER_OWN_WRITE_MS + 1)
    await fetchAPI("/api/financial/counterparty-parties?case_id=c1")
    expect(fetch.mock.calls[2][1].headers["X-Financial-View-Accept"]).toBe("updating")
  } finally {
    vi.useRealTimers()
  }
})
it("keeps asking to be answered as updating after the page posts its speed records", async () => {
  const { clearUpdatingViews, noteOwnWrite } = await import("./financial-view-updates")
  clearUpdatingViews()
  vi.useFakeTimers()
  try {
    noteOwnWrite(0) // long ago
    const fetch = vi.fn().mockImplementation(() => Promise.resolve(new Response("{}", { status: 202 })))
    vi.stubGlobal("fetch", fetch)
    await fetchAPI("/api/request-speed/page-views", { method: "POST", body: { views: [] } })
    await fetchAPI("/api/evidence?case_id=c1&include_reading_versions=true&financial_only=true")
    expect(fetch.mock.calls[1][1].headers["X-Financial-View-Accept"]).toBe("updating")
  } finally {
    vi.useRealTimers()
  }
})
it("ignores an answer to an earlier request that arrives after a later one", async () => {
  const { clearUpdatingViews, nextRequestNumber, noteViewAnswer, updatingViews } = await import("./financial-view-updates")
  clearUpdatingViews()
  const earlier = nextRequestNumber()
  const later = nextRequestNumber()
  noteViewAnswer("/api/financial/ledger?case_id=c1", "2026-10-31T07:15:00+00:00", later)
  noteViewAnswer("/api/financial/ledger?case_id=c1", undefined, earlier)
  expect(updatingViews().get("/api/financial/ledger?case_id=c1")).toBe("2026-10-31T07:15:00+00:00")
})
