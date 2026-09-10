import { render, screen, fireEvent, waitFor } from "@testing-library/react"
import { it, expect, vi, afterEach } from "vitest"
import { LedgerExportButton } from "./LedgerExportButton"
afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
  localStorage.clear()
})
function mount(
  change: Record<string, string> = {},
  tableView?: import("../lib/ledger-table-view").LedgerTableView
) {
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
      tableView={tableView}
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

it("includes original files only when selected and confirmed by the response", async () => {
  const { fetch, makeUrl } = mount({ "X-Loupe-Source-Files": "true" })
  fireEvent.click(
    screen.getByLabelText(
      "Include original source files with fresh hash checks"
    )
  )
  expect(screen.getByText(/complete referenced files/)).toBeVisible()
  fireEvent.click(
    screen.getByRole("button", { name: "Download ledger snapshot" })
  )
  expect(await screen.findByText(/Download started/)).toBeInTheDocument()
  expect(String(fetch.mock.calls[0][0])).toContain("include_source_files=true")
  expect(makeUrl).toHaveBeenCalledTimes(1)
})
it("refuses an export that omitted requested original files", async () => {
  const { makeUrl } = mount({ "X-Loupe-Source-Files": "false" })
  fireEvent.click(
    screen.getByLabelText(
      "Include original source files with fresh hash checks"
    )
  )
  fireEvent.click(
    screen.getByRole("button", { name: "Download ledger snapshot" })
  )
  expect(
    await screen.findByText(/different filters or in an unexpected format/)
  ).toBeVisible()
  expect(makeUrl).not.toHaveBeenCalled()
})
it("refuses an unexpected original-file bundle", async () => {
  const { makeUrl } = mount({ "X-Loupe-Source-Files": "true" })
  fireEvent.click(
    screen.getByRole("button", { name: "Download ledger snapshot" })
  )
  expect(
    await screen.findByText(/different filters or in an unexpected format/)
  ).toBeVisible()
  expect(makeUrl).not.toHaveBeenCalled()
})

it("requests a PDF only when selected and requires the PDF response marker", async () => {
  const { fetch, makeUrl } = mount()
  fireEvent.click(screen.getByLabelText("Include a paginated PDF report"))
  fireEvent.click(
    screen.getByRole("button", { name: "Download ledger snapshot" })
  )
  await screen.findByText(/different filters or in an unexpected format/)
  expect(String(fetch.mock.calls[0][0])).toContain("include_pdf=true")
  expect(makeUrl).not.toHaveBeenCalled()
})

it("captures the full table settings and rejects a different returned view", async () => {
  const view = {
    search: "Office cost",
    currency: "GBP",
    direction: "debit",
    proof: "p3",
    sort: "amount-desc",
  }
  const { fetch, click } = mount(
    { "X-Loupe-Table-View": JSON.stringify({ ...view, sort: "ledger" }) },
    view
  )
  fireEvent.click(
    screen.getByRole("button", { name: "Download this table view" })
  )
  expect(await screen.findByText(/different filters/)).toBeInTheDocument()
  expect(
    JSON.parse(
      new URL(
        String(fetch.mock.calls[0][0]),
        "http://localhost"
      ).searchParams.get("table_view")!
    )
  ).toEqual(view)
  expect(click).not.toHaveBeenCalled()
})
it("downloads a matching recorded table view", async () => {
  const view = {
    search: "Office cost",
    currency: "GBP",
    direction: "debit",
    proof: "p3",
    sort: "amount-desc",
  }
  const { click } = mount({ "X-Loupe-Table-View": JSON.stringify(view) }, view)
  fireEvent.click(
    screen.getByRole("button", { name: "Download this table view" })
  )
  expect(await screen.findByText(/Download started/)).toBeInTheDocument()
  expect(click).toHaveBeenCalledTimes(1)
})
