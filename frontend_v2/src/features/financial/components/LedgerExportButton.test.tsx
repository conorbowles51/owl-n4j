import { render, screen, fireEvent, waitFor } from "@testing-library/react"
import { it, expect, vi, afterEach } from "vitest"
import { LedgerExportButton } from "./LedgerExportButton"
afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
  localStorage.clear()
})
function mount(change: Record<string, string> = {}) {
  const headers = {
    "content-type": "application/zip",
    "X-Loupe-Case-Id": "case-a",
    "X-Loupe-Account-Id": "account-a",
    "X-Loupe-Start-Date": "2026-01-01",
    "X-Loupe-End-Date": "2026-01-31",
    ...change,
  }
  const fetch = vi
    .spyOn(globalThis, "fetch")
    .mockResolvedValue(new Response("zip-bytes", { headers }))
  const makeUrl = vi.fn(() => "blob:export")
  vi.stubGlobal(
    "URL",
    class extends URL {
      static createObjectURL = makeUrl
      static revokeObjectURL = vi.fn()
    }
  )
  const click = vi
    .spyOn(HTMLAnchorElement.prototype, "click")
    .mockImplementation(() => {})
  render(
    <LedgerExportButton
      caseId="case-a"
      params={{
        accountId: "account-a",
        startDate: "2026-01-01",
        endDate: "2026-01-31",
      }}
    />
  )
  return { fetch, makeUrl, click }
}
it("downloads binary without parsing and sends authenticated applied scope", async () => {
  localStorage.setItem("authToken", "fixture-token")
  const { fetch, makeUrl, click } = mount()
  fireEvent.click(
    screen.getByRole("button", { name: "Download ledger snapshot" })
  )
  expect(await screen.findByText(/Download started/)).toBeInTheDocument()
  expect(String(fetch.mock.calls[0][0])).toContain(
    "account_id=account-a&start_date=2026-01-01&end_date=2026-01-31"
  )
  expect(fetch.mock.calls[0][1]?.headers).toEqual({
    Authorization: "Bearer fixture-token",
  })
  expect(makeUrl).toHaveBeenCalledTimes(1)
  expect(click).toHaveBeenCalledTimes(1)
})
it.each<Record<string, string>>([
  { "X-Loupe-Case-Id": "other" },
  { "X-Loupe-Account-Id": "other" },
  { "X-Loupe-Start-Date": "" },
  { "content-type": "text/html" },
])("refuses mismatched binary response %j", async (change) => {
  const { makeUrl } = mount(change)
  fireEvent.click(
    screen.getByRole("button", { name: "Download ledger snapshot" })
  )
  expect(
    await screen.findByText(/different filters or in an unexpected format/)
  ).toBeInTheDocument()
  expect(makeUrl).not.toHaveBeenCalled()
})
it("aborts an unfinished download when scope is unmounted", async () => {
  let signal: AbortSignal | undefined
  vi.spyOn(globalThis, "fetch").mockImplementation((_url, options) => {
    signal = options?.signal as AbortSignal
    return new Promise(() => {})
  })
  const { unmount } = render(<LedgerExportButton caseId="case-a" params={{}} />)
  fireEvent.click(
    screen.getByRole("button", { name: "Download ledger snapshot" })
  )
  await waitFor(() => expect(signal).toBeDefined())
  unmount()
  expect(signal?.aborted).toBe(true)
})
