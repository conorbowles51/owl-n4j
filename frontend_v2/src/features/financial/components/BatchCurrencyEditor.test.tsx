import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { beforeEach, expect, it, vi } from "vitest"
import { fetchAPI } from "@/lib/api-client"
import { BatchCurrencyEditor } from "./BatchCurrencyEditor"
vi.mock("@/lib/api-client", () => ({ fetchAPI: vi.fn() }))
beforeEach(() => vi.resetAllMocks())
const items = Array.from({ length: 588 }, (_, i) => ({
  id: `item-${i}`,
  filename: `${i} ${i < 350 ? "MXN" : "USD"} statement.pdf`,
  account: "0012345",
  period_start: "2024-09-01",
  currency: "EUR",
  status: i === 587 ? "imported" : "ready",
  currency_revision: "a".repeat(64),
}))
function mount() {
  const saved = vi.fn()
  render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <BatchCurrencyEditor caseId="case" batchId="batch" onSaved={saved} />
    </QueryClientProvider>
  )
  return saved
}
it("selects matching statements across all pages, retains hidden selections and applies only those currencies", async () => {
  let sent: unknown
  vi.mocked(fetchAPI).mockImplementation(async (url, options) => {
    if (options?.method) {
      sent = options.body
      return {
        case_id: "case",
        batch_id: "batch",
        updated: 350,
        currency: "MXN",
      } as never
    }
    const offset = Number(
      new URL(url, "http://localhost").searchParams.get("offset")
    )
    return {
      case_id: "case",
      id: "batch",
      total: items.length,
      items: items.slice(offset, offset + 500),
    } as never
  })
  const saved = mount()
  fireEvent.click(
    screen.getByRole("button", { name: "Set currency for selected statements" })
  )
  await screen.findByRole("button", {
    name: "Select all 587 matching statements",
  })
  fireEvent.change(screen.getByLabelText("Find statements for currency"), {
    target: { value: "MXN" },
  })
  fireEvent.click(
    screen.getByRole("button", { name: "Select all 350 matching statements" })
  )
  fireEvent.change(screen.getByLabelText("Find statements for currency"), {
    target: { value: "USD" },
  })
  expect(screen.getByText("350 selected · 350 hidden by search")).toBeVisible()
  fireEvent.click(
    screen.getByRole("button", { name: "Apply MXN to 350 statements" })
  )
  await screen.findByText(/MXN saved for 350/)
  expect(sent).toEqual({
    currency: "MXN",
    statements: items
      .slice(0, 350)
      .map((item) => ({ id: item.id, revision: item.currency_revision })),
  })
  expect(saved).toHaveBeenCalledTimes(1)
})
it("retains selection on failure and rejects another case's list", async () => {
  vi.mocked(fetchAPI).mockImplementation(async (_url, options) => {
    if (options?.method) throw Error("A selected statement changed.")
    return {
      case_id: "case",
      id: "batch",
      total: 1,
      items: [items[0]],
    } as never
  })
  mount()
  fireEvent.click(
    screen.getByRole("button", { name: "Set currency for selected statements" })
  )
  fireEvent.click(
    await screen.findByRole("button", {
      name: "Select all 1 matching statements",
    })
  )
  fireEvent.click(
    screen.getByRole("button", { name: "Apply MXN to 1 statements" })
  )
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Your selection is kept"
  )
  expect(screen.getByRole("checkbox")).toBeChecked()
  vi.mocked(fetchAPI).mockResolvedValue({
    case_id: "other",
    id: "batch",
    total: 0,
    items: [],
  } as never)
  fireEvent.click(screen.getByRole("button", { name: "Refresh currency list" }))
  await waitFor(() =>
    expect(
      screen
        .getAllByRole("alert")
        .some((node) => node.textContent?.includes("another batch"))
    ).toBe(true)
  )
})
