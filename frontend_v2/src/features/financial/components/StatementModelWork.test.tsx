import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { beforeEach, expect, it, vi } from "vitest"
import { fetchAPI } from "@/lib/api-client"
import { StatementModelWorkMark } from "./StatementModelWork"
import type { StatementModelWork } from "../lib/statement-model-work"

vi.mock("@/lib/api-client", () => ({ fetchAPI: vi.fn() }))

const work = (overrides: Partial<StatementModelWork> = {}): StatementModelWork => ({
  status: "not_confirmed",
  model: "Claude",
  saved: false,
  for_person: "Neil Byrne",
  calls: [
    {
      id: "j1",
      rule_id: "model.statement_account",
      status: "open",
      summary: "Claude, working for Neil Byrne, changed this statement's details. This moved the statement to another account.",
    },
  ],
  ...overrides,
})
const mount = (node: React.ReactNode) =>
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      {node}
    </QueryClientProvider>
  )
beforeEach(() => vi.mocked(fetchAPI).mockReset())

it("says Claude changed the details, not saved the payments, and a person confirms it", async () => {
  vi.mocked(fetchAPI).mockResolvedValue(work({ status: "confirmed", confirmed_by: "Alex" }))
  const onConfirmed = vi.fn()
  mount(<StatementModelWorkMark caseId="c1" sourceDocumentId="s1" work={work()} canEdit onConfirmed={onConfirmed} />)
  expect(screen.getByText(/Details changed by Claude for Neil Byrne · not confirmed/)).toBeTruthy()
  expect(screen.getByText(/account and details against the page/)).toBeTruthy()
  expect(screen.queryByText(/Saved by Claude/)).toBeNull()
  fireEvent.click(screen.getByText("What was done"))
  expect(screen.getByText(/moved the statement to another account/)).toBeTruthy()
  fireEvent.click(screen.getByRole("button", { name: /confirm/ }))
  await waitFor(() => expect(onConfirmed).toHaveBeenCalled())
  expect(vi.mocked(fetchAPI).mock.calls[0][0]).toBe("/api/financial/judgements/statements/s1/confirm?case_id=c1")
})

it("keeps the saved wording when Claude saved the payments", () => {
  mount(
    <StatementModelWorkMark caseId="c1" sourceDocumentId="s1" work={work({ saved: true })} canEdit={false} onConfirmed={() => {}} />
  )
  expect(screen.getByText(/Saved by Claude for Neil Byrne · not confirmed/)).toBeTruthy()
})
