import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { MemoryRouter } from "react-router-dom"
import { beforeEach, expect, it, vi } from "vitest"

const api = vi.hoisted(() => ({
  getPaymentCrossing: vi.fn(),
  createPayeeDossier: vi.fn(),
  getFinancialPresence: vi.fn(),
}))
vi.mock("@/features/phones/api", () => api)

import { PaymentPhoneActivity } from "./PaymentPhoneActivity"
import { NoFinancialEvidenceNotice } from "./NoFinancialEvidenceNotice"

const CASE = "cded78d0-e659-44cc-940d-d8f8c8012760"
const TXN = "11111111-2222-3333-4444-555555555555"
const wrap = (ui: React.ReactNode) => render(
  <QueryClientProvider client={new QueryClient()}><MemoryRouter>{ui}</MemoryRouter></QueryClientProvider>)

beforeEach(() => { Object.values(api).forEach((f) => f.mockReset()) })

it("XF-1: lists the days around a payment as day words with Conversations links, never a time of day", async () => {
  api.getPaymentCrossing.mockResolvedValue({
    state: "linked", sentence: "Ana Synthetic on the phones around this payment.", total: 4,
    conversations_href: `/cases/${CASE}/conversations?people=a&from=2023-03-13&to=2023-03-15`,
    payment_date: "2023-03-14", people: [{ id: "d1", name: "Ana Synthetic" }],
    days: [
      { offset: -1, words: "1 day before", date: "2023-03-13", count: 1, conversations_href: "/x?from=2023-03-13" },
      { offset: 0, words: "same day", date: "2023-03-14", count: 2, conversations_href: "/x?from=2023-03-14" },
    ],
  })
  wrap(<PaymentPhoneActivity caseId={CASE} transactionId={TXN} />)
  expect(await screen.findByText("1 day before: 1 message or call")).toBeInTheDocument()
  expect(screen.getByText("same day: 2 messages and calls").closest("a")).toHaveAttribute("href", "/x?from=2023-03-14")
  expect(screen.getByText("Open all 4 in Conversations")).toBeInTheDocument()
  expect(screen.getByText("Lanes for Ana Synthetic on the payment day").closest("a")?.getAttribute("href"))
    .toContain("day=2023-03-14")
  expect(screen.getByTestId("payment-phone-activity").textContent).not.toMatch(/\d:\d\d|AM|PM/)
})

it("XF-1: an unlinked payee says so and offers a dossier, made only on a click", async () => {
  api.getPaymentCrossing.mockResolvedValue({
    state: "unlinked", sentence: "This payee is not linked to a person yet.", payee_dossier_offer: true,
    counterparty: { label: "Corner Shop" }, days: [],
  })
  api.createPayeeDossier.mockResolvedValue({ id: "dz", display_name: "Corner Shop" })
  wrap(<PaymentPhoneActivity caseId={CASE} transactionId={TXN} />)
  const make = await screen.findByRole("button", { name: "Make a dossier for Corner Shop" })
  expect(api.createPayeeDossier).not.toHaveBeenCalled()
  fireEvent.click(make)
  expect(await screen.findByRole("status")).toHaveTextContent("Dossier made for Corner Shop.")
  expect(api.createPayeeDossier).toHaveBeenCalledWith(CASE, TXN)
})

it("XF-1: shows nothing when the case has no phones, and nothing for a row without a payment id", async () => {
  api.getPaymentCrossing.mockResolvedValue({ state: "no_phones", days: [] })
  const { container } = wrap(<PaymentPhoneActivity caseId={CASE} transactionId={TXN} />)
  await waitFor(() => expect(api.getPaymentCrossing).toHaveBeenCalled())
  await waitFor(() => expect(container.querySelector("[data-testid=payment-phone-activity]")).toBeNull())
  api.getPaymentCrossing.mockClear()
  wrap(<PaymentPhoneActivity caseId={CASE} transactionId="draft-1" />)
  expect(api.getPaymentCrossing).not.toHaveBeenCalled()
})

it("SA-7: the Financial page says there is no financial evidence, never 0 payments, and nothing once there is", async () => {
  api.getFinancialPresence.mockResolvedValue({
    has_financial_evidence: false, financial_sentence: "No financial evidence in this case. Add bank statements from Evidence.",
  })
  wrap(<NoFinancialEvidenceNotice caseId={CASE} />)
  const note = await screen.findByTestId("no-financial-evidence")
  expect(note).toHaveTextContent("No financial evidence in this case.")
  expect(note.textContent).not.toMatch(/0 payments/)
  api.getFinancialPresence.mockResolvedValue({ has_financial_evidence: true, financial_sentence: null })
  const other = wrap(<NoFinancialEvidenceNotice caseId="other" />)
  await waitFor(() => expect(api.getFinancialPresence).toHaveBeenCalledWith("other"))
  expect(other.container.querySelector("[data-testid=no-financial-evidence]")).toBeNull()
})
