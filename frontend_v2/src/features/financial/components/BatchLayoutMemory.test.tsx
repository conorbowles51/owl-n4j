import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { fireEvent, render, screen } from "@testing-library/react"
import { beforeEach, expect, it, vi } from "vitest"
import { fetchAPI } from "@/lib/api-client"
import { BatchLayoutMemory } from "./BatchLayoutMemory"
vi.mock("@/lib/api-client", () => ({ fetchAPI: vi.fn() }))
beforeEach(() => vi.resetAllMocks())

const statements = [1, 2, 3].map((n) => ({
  item_id: `item-${n}`,
  file_id: `file-${n}`,
  statement_id: String(n).repeat(64),
  filename: `statement-${n}.pdf`,
  period_start: `2024-0${n}-01`,
  period_end: `2024-0${n}-28`,
  money_proved: n !== 3,
}))
function listing(confirmed: boolean) {
  return {
    case_id: "case",
    batch_id: "batch",
    groups: [
      {
        key: "k".repeat(64),
        field: "holder",
        label: "account holder",
        account: "0012345678",
        printed: ["SAMPLE COMPANY"],
        proposal: "SAMPLE COMPANY",
        proposal_basis: "printed_addressee",
        confirmations: confirmed
          ? [
              {
                id: "conf-1",
                value: "SAMPLE COMPANY LTD",
                confirmed_at: "2026-10-07T00:00:00Z",
                confirmed_by: { name: "Investigator" },
              },
            ]
          : [],
        conflict: false,
        statement_count: 3,
        money_proved_count: 2,
        statements,
      },
    ],
  }
}
function mount() {
  const saved = vi.fn()
  render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <BatchLayoutMemory caseId="case" batchId="batch" onSaved={saved} />
    </QueryClientProvider>
  )
  return saved
}

it("confirms one prefilled value for every statement of the group", async () => {
  let sent: unknown
  let confirmed = false
  vi.mocked(fetchAPI).mockImplementation(async (url, options) => {
    if (options?.method) {
      sent = { url, body: options.body }
      confirmed = true
      return {
        case_id: "case",
        already_confirmed: false,
        refreshed: { refreshed: 3 },
      } as never
    }
    return listing(confirmed) as never
  })
  const saved = mount()
  fireEvent.click(
    screen.getByRole("button", {
      name: "Confirm details once for matching statements",
    })
  )
  const input = await screen.findByLabelText(
    "Account holder shown on the statements"
  )
  expect(input).toHaveValue("SAMPLE COMPANY")
  expect(screen.getByText(/2 of 3 have balances/)).toBeVisible()
  fireEvent.change(input, { target: { value: "SAMPLE COMPANY LTD" } })
  fireEvent.click(screen.getByRole("button", { name: "Confirm for 3 statements" }))
  await screen.findByText(/SAMPLE COMPANY LTD confirmed as the account holder for 3 statements/)
  expect(sent).toEqual({
    url: "/api/financial/statement-import/layout-memory/confirm?case_id=case",
    body: {
      file_id: "file-1",
      statement_id: "1".repeat(64),
      field: "holder",
      value: "SAMPLE COMPANY LTD",
      key: "k".repeat(64),
      request_id: expect.any(String),
    },
  })
  expect(saved).toHaveBeenCalled()
  await screen.findByText(/Confirmed: SAMPLE COMPANY LTD by Investigator/)
})

it("withdraws a confirmation only with a reason", async () => {
  let sent: unknown
  vi.mocked(fetchAPI).mockImplementation(async (url, options) => {
    if (options?.method) {
      sent = { url, body: options.body }
      return {} as never
    }
    return listing(true) as never
  })
  mount()
  fireEvent.click(
    screen.getByRole("button", {
      name: "Confirm details once for matching statements",
    })
  )
  const button = await screen.findByRole("button", {
    name: "Withdraw this confirmation",
  })
  expect(button).toBeDisabled()
  fireEvent.change(screen.getByLabelText("Reason to withdraw"), {
    target: { value: "Wrong company" },
  })
  fireEvent.click(button)
  await screen.findByText(/Confirmation withdrawn/)
  expect(sent).toEqual({
    url: "/api/financial/statement-import/layout-memory/conf-1/withdraw?case_id=case",
    body: { reason: "Wrong company" },
  })
})
