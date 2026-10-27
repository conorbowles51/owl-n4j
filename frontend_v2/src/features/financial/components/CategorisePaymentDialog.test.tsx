import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { afterEach, expect, it, vi } from "vitest"
import { fetchAPI } from "@/lib/api-client"
import { readSelectedPayments } from "../lib/selected-payment-source"
import { CategorisePaymentDialog } from "./CategorisePaymentDialog"

vi.mock("@/lib/api-client", async (original) => ({
  ...(await original<typeof import("@/lib/api-client")>()),
  fetchAPI: vi.fn(),
}))
vi.mock("../lib/selected-payment-source", () => ({ readSelectedPayments: vi.fn() }))
vi.mock("../hooks/use-financial-access", () => ({ useFinancialAccess: () => ({ canEdit: true }) }))
afterEach(cleanup)

it("suggests Loupe's category, picks by key, applies the choice to the similar payments and makes a rule, with the saved id", async () => {
  const calls: { url: string; body: unknown }[] = []
  vi.mocked(readSelectedPayments).mockResolvedValue([
    {
      transaction: {
        key: "t1",
        case_id: "case",
        account_label: "BBVA 0118",
        description: "PAGO FACTURA 31102",
        ordering_date: "2023-10-31",
        amount_minor: "23484038",
        currency: "MXN",
        direction: "debit",
        category: "Payments",
        label_version: 2,
        label_sources: { category: { source: "description", explanation: "PAGO FACTURA means invoice payment" } },
      },
    },
  ] as unknown as Awaited<ReturnType<typeof readSelectedPayments>>)
  vi.mocked(fetchAPI).mockImplementation(async (url, options) => {
    calls.push({ url, body: options?.body })
    if (url.includes("category-library")) return { case_id: "case", categories: [{ name: "Payments", color: "#8060a9" }, { name: "Transfers", color: "#8060a9" }] }
    if (url.includes("/like"))
      return { case_id: "case", count: 14, basis: "same description", transaction_ids: ["l1", "l2"], first_date: "2023-02-01", last_date: "2023-11-30", examples: [{ id: "l1", date: "2023-02-01", description: "PAGO FACTURA 1" }] }
    if (url.includes("preview")) return { case_id: "case", revision: "b".repeat(64), count: 1 }
    if (url.includes("confirm")) return { case_id: "case", updated: 1, replacements: [{ previous_id: "t1", id: "t1-new" }] }
    if (url.includes("apply-like")) return { case_id: "case", updated: 14 }
    if (url.includes("/payment-categories/rules?")) return { case_id: "case", rule: { id: "r1" } }
    throw Error(url)
  })
  const onSaved = vi.fn()
  const onClose = vi.fn()
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <CategorisePaymentDialog caseId="case" ids={["t1"]} onMoreFields={vi.fn()} onSaved={onSaved} onClose={onClose} />
    </QueryClientProvider>
  )
  await screen.findByRole("region", { name: "Loupe suggests" })
  expect(screen.getByText(/PAGO FACTURA means invoice payment/)).toBeTruthy()
  await screen.findByText("Also apply to the 14 other payments like this")
  // Suggestion is pre-chosen; key 2 picks the next tile (Transfers).
  expect(screen.getByRole("button", { name: /^Payments/ }).getAttribute("aria-pressed")).toBe("true")
  fireEvent.keyDown(window, { key: "2" })
  expect(screen.getByRole("button", { name: /^Transfers/ }).getAttribute("aria-pressed")).toBe("true")
  fireEvent.click(screen.getByRole("checkbox", { name: /Make this a rule for future statements too/ }))
  fireEvent.click(screen.getByRole("button", { name: "Save 15 payments" }))
  await waitFor(() => expect(onClose).toHaveBeenCalled())
  expect(calls.find((c) => c.url.includes("confirm"))?.body).toMatchObject({ changes: { category: "Transfers" }, transactions: [{ id: "t1", version: 2 }] })
  expect(calls.find((c) => c.url.includes("apply-like"))?.body).toEqual({ transaction_id: "t1-new", category: "Transfers", transaction_ids: ["l1", "l2"] })
  expect(calls.find((c) => c.url.includes("/payment-categories/rules?"))?.body).toEqual({ transaction_id: "t1-new", category: "Transfers" })
  expect(onSaved).toHaveBeenCalledWith([{ previous_id: "t1", id: "t1-new" }])
})
