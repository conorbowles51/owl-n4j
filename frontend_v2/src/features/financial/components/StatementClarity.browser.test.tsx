import "@/styles/globals.css"
import { page } from "vitest/browser"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react"
import { afterEach, expect, it, vi } from "vitest"
import { MemoryRouter, useLocation } from "react-router-dom"
import { fetchAPI } from "@/lib/api-client"
import { OverviewStatementCoverage } from "./OverviewStatementCoverage"
import { StatementFilesPanel } from "./StatementFilesPanel"
import { StatementCurrencySource } from "./StatementCurrencySource"
import { StatementSourceTools } from "./StatementSourceTools"
vi.mock("@/lib/api-client", async (original) => ({
  ...(await original<typeof import("@/lib/api-client")>()),
  fetchAPI: vi.fn(),
}))
vi.mock("./StatementRecoveryPanel", () => ({
  StatementRecoveryPanel: () => null,
}))
vi.mock("@/features/evidence/components/ResumableUploadsPanel", () => ({
  ResumableUploadsPanel: () => null,
}))
vi.mock("../hooks/use-financial-access", () => ({
  useFinancialAccess: () => ({ canEdit: true, canUpload: true }),
}))
afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})
function Location() {
  const location = useLocation()
  return (
    <output aria-label="Destination">
      {location.pathname}
      {location.search}
    </output>
  )
}
function mount(children: React.ReactNode) {
  return render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <MemoryRouter>
        {children}
        <Location />
      </MemoryRouter>
    </QueryClientProvider>
  )
}
it.each([1280, 390])(
  "shows missing months and opens account review at %ipx",
  async (width) => {
    await page.viewport(width, 900)
    vi.mocked(fetchAPI).mockResolvedValue({
      case_id: "case",
      offset: 0,
      has_more: false,
      applied: false,
      limitation: "Printed dates only",
      items: [
        {
          account_id: "account",
          label: "Example Bank · 1234",
          available: true,
          reason: null,
          periods: [],
          currencies: [
            {
              currency: "USD",
              period_count: 22,
              covered_days: 671,
              uncovered_days: 59,
              windows: [
                { start: "2024-01-01", end: "2024-12-31", period_ids: [] },
                { start: "2025-03-01", end: "2025-12-31", period_ids: [] },
              ],
              gaps: [{ start: "2025-01-01", end: "2025-02-28", days: 59 }],
              overlaps: [],
            },
          ],
        },
      ],
    })
    mount(<OverviewStatementCoverage caseId="case" active />)
    await screen.findByText("USD · 2 of 24 months missing")
    expect(screen.getByText("Missing: Jan 2025, Feb 2025.")).toBeVisible()
    expect(
      screen.getByText(/Earlier and later months have not been checked/)
    ).toBeVisible()
    await page.screenshot({ path: `/private/tmp/loupe-months-${width}.png` })
    fireEvent.click(
      screen.getByRole("button", { name: "Check dates and missing statements" })
    )
    expect(screen.getByLabelText("Destination")).toHaveTextContent("accounts=1")
  }
)
it.each([1280, 390])(
  "opens one group review for ready files without importing or including duplicates at %ipx",
  async (width) => {
    await page.viewport(width, 900)
    const writes: unknown[] = []
    vi.mocked(fetchAPI).mockImplementation(async (url, options) => {
      if (options?.method === "POST") {
        writes.push(options.body)
        return { id: "group", case_id: "case" }
      }
      if (url.includes("statement-import/files"))
        return {
          case_id: "case",
          truncated: false,
          files: [
            {
              evidence_file_id: "ready",
              current_transactions: 0,
              periods: [],
              prepared_periods: 128,
              available_periods: 128,
            },
            {
              evidence_file_id: "duplicate",
              current_transactions: 0,
              periods: [],
              prepared_periods: 1,
              ignored_periods: 1,
            },
          ],
        }
      if (url.startsWith("/api/evidence?"))
        return {
          files: ["ready", "duplicate"].map((id) => ({
            id,
            case_id: "case",
            original_filename: `${id}.pdf`,
            status: "processed",
          })),
        }
      return {}
    })
    mount(<StatementFilesPanel caseId="case" register />)
    const button = await screen.findByRole("button", {
      name: "Review and save 128 ready statements together",
    })
    expect(screen.getByText(/Their payments are not saved yet/)).toBeVisible()
    expect(
      screen.getByText("128 statements ready to save · not saved yet")
    ).toBeVisible()
    expect(button.getBoundingClientRect().right).toBeLessThanOrEqual(width)
    await page.screenshot({ path: `/private/tmp/loupe-ready-${width}.png` })
    fireEvent.click(button)
    await waitFor(() =>
      expect(screen.getByLabelText("Destination")).toHaveTextContent(
        "batch=group"
      )
    )
    expect(writes).toEqual([
      { request_id: expect.any(String), file_ids: ["ready"], folder_ids: [] },
    ])
  }
)
it("copies source text beside an unfinished correction without leaving the review", async () => {
  await page.viewport(390, 844)
  const copied = vi.spyOn(navigator.clipboard, "writeText").mockResolvedValue()
  mount(
    <>
      <input aria-label="Correction" defaultValue="Unfinished edit" />
      <StatementSourceTools
        fileId="source"
        page={2}
        text="Example payee 123.45"
      />
    </>
  )
  fireEvent.click(screen.getByRole("button", { name: "Copy page text" }))
  const text = screen.getByLabelText(
    "Read page text · page 2"
  ) as HTMLTextAreaElement
  text.focus()
  text.setSelectionRange(0, 13)
  fireEvent.click(
    screen.getByRole("button", { name: "Copy selected text or whole page" })
  )
  await waitFor(() => expect(copied).toHaveBeenCalledWith("Example payee"))
  expect(screen.getByLabelText("Correction")).toHaveValue("Unfinished edit")
})

it.each([1280, 390])(
  "keeps currency and original page navigation together at %ipx",
  async (width) => {
    await page.viewport(width, 900)
    const requests: string[] = []
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      requests.push(String(input))
      return new Response(
        '<svg xmlns="http://www.w3.org/2000/svg" width="400" height="500"><text x="20" y="40">Example statement: Currency USD</text></svg>',
        { headers: { "Content-Type": "image/svg+xml" } }
      )
    })
    mount(
      <StatementCurrencySource
        fileId="synthetic-source"
        filename="Example statement.pdf"
        pages={[2, 4]}
      >
        <label>
          Statement currency{" "}
          <select aria-label="Statement currency" defaultValue="">
            <option value="">Choose currency</option>
            <option value="USD">USD</option>
          </select>
        </label>
      </StatementCurrencySource>
    )
    await screen.findByRole("img", { name: "Page 2 of the source document" })
    await page.getByRole("button", { name: "Next page", exact: true }).click()
    await screen.findByRole("img", { name: "Page 4 of the source document" })
    expect(screen.getByLabelText("Statement currency")).toBeVisible()
    expect(
      screen.getByRole("button", { name: "Next page" })
    ).toBeDisabled()
    await page
      .getByRole("button", { name: "Previous page", exact: true })
      .click()
    await screen.findByRole("img", { name: "Page 2 of the source document" })
    expect(
      requests.some((url) => url.includes("/synthetic-source/page/4/image"))
    ).toBe(true)
    expect(document.documentElement.scrollWidth).toBeLessThanOrEqual(width)
    await page.screenshot({
      path: `/private/tmp/loupe-currency-source-${width}.png`,
    })
  }
)
