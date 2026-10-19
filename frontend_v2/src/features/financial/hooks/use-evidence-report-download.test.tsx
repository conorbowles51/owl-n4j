import { act, renderHook } from "@testing-library/react"
import { afterEach, beforeEach, expect, it, vi } from "vitest"
import { useEvidenceReportDownload } from "./use-evidence-report-download"

const NativeURL = URL
const create = vi.fn(() => "blob:synthetic-report")
const click = vi.fn()
beforeEach(() => {
  localStorage.setItem("authToken", "synthetic-session")
  create.mockClear()
  click.mockClear()
  vi.stubGlobal(
    "URL",
    class extends NativeURL {
      static createObjectURL = create
      static revokeObjectURL = vi.fn()
    }
  )
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(click)
})
afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})
const params = new URLSearchParams({
  case_id: "case-a",
  min_amount: "100",
  max_amount: "200",
})

it("downloads with the current credentials and exact filters while blocking a repeated click", async () => {
  let resolve!: (value: Response) => void
  const fetch = vi.fn<typeof globalThis.fetch>(
    () =>
      new Promise<Response>((done) => {
        resolve = done
      })
  )
  vi.stubGlobal("fetch", fetch)
  const { result } = renderHook(() => useEvidenceReportDownload("case-a"))
  let first!: Promise<void>
  act(() => {
    first = result.current.download(params)
  })
  await act(async () => result.current.download(params))
  expect(fetch).toHaveBeenCalledTimes(1)
  expect(fetch.mock.calls[0][0]).toContain("min_amount=100&max_amount=200")
  expect(fetch.mock.calls[0][1]).toMatchObject({
    headers: { Authorization: "Bearer synthetic-session" },
  })
  await act(async () => {
    resolve(
      new Response("%PDF-1.7 synthetic", {
        headers: { "content-type": "application/pdf" },
      })
    )
    await first
  })
  expect(create).toHaveBeenCalledOnce()
  expect(click).toHaveBeenCalledOnce()
  expect(result.current.busy).toBe(false)
  expect(result.current.error).toBe("")
})

it("shows a failed request without opening a report and allows a later retry", async () => {
  const fetch = vi
    .fn()
    .mockResolvedValueOnce(
      new Response(JSON.stringify({ detail: "Case access changed" }), {
        status: 403,
      })
    )
    .mockResolvedValueOnce(
      new Response("<html>Printable report</html>", {
        headers: { "content-type": "text/html; charset=utf-8" },
      })
    )
  vi.stubGlobal("fetch", fetch)
  const { result } = renderHook(() => useEvidenceReportDownload("case-a"))
  await act(async () => result.current.download(params))
  expect(result.current.error).toBe("Case access changed")
  expect(create).not.toHaveBeenCalled()
  await act(async () => result.current.download(params))
  expect(click).toHaveBeenCalledOnce()
  expect(result.current.error).toBe("")
})

it("discards a response from an earlier case and starts the new case without its busy state", async () => {
  let resolve!: (value: Response) => void
  const fetch = vi.fn<typeof globalThis.fetch>(
    () =>
      new Promise<Response>((done) => {
        resolve = done
      })
  )
  vi.stubGlobal("fetch", fetch)
  const { result, rerender } = renderHook(
    ({ id }) => useEvidenceReportDownload(id),
    { initialProps: { id: "case-a" } }
  )
  let pending!: Promise<void>
  act(() => {
    pending = result.current.download(params)
  })
  rerender({ id: "case-b" })
  expect(result.current.busy).toBe(false)
  await act(async () => {
    resolve(
      new Response("%PDF-1.7 old case", {
        headers: { "content-type": "application/pdf" },
      })
    )
    await pending
  })
  expect(create).not.toHaveBeenCalled()
  expect(result.current.error).toBe("")
})

it("discards a response when the signed-in session has changed", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => {
      localStorage.setItem("authToken", "new-session")
      return new Response("%PDF-1.7 old session", {
        headers: { "content-type": "application/pdf" },
      })
    })
  )
  const { result } = renderHook(() => useEvidenceReportDownload("case-a"))
  await act(async () => result.current.download(params))
  expect(create).not.toHaveBeenCalled()
  expect(result.current.busy).toBe(false)
})

it("rejects empty reports and non-report responses", async () => {
  const fetch = vi
    .fn()
    .mockResolvedValueOnce(
      new Response("", { headers: { "content-type": "application/pdf" } })
    )
    .mockResolvedValueOnce(
      new Response("{}", { headers: { "content-type": "application/json" } })
    )
  vi.stubGlobal("fetch", fetch)
  const { result } = renderHook(() => useEvidenceReportDownload("case-a"))
  await act(async () => result.current.download(params))
  expect(result.current.error).toContain("empty")
  await act(async () => result.current.download(params))
  expect(result.current.error).toContain("did not return a report")
  expect(create).not.toHaveBeenCalled()
})
