vi.mock("@/lib/api-client", () => ({ fetchAPI: vi.fn() }))

import { act, fireEvent, render, screen } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { afterEach, expect, it, vi } from "vitest"
import { fetchAPI } from "@/lib/api-client"
import { ReadingJudgements } from "./JudgementCalls"

afterEach(() => vi.useRealTimers())

it("the holder goes to the preview once typing settles, not on every keystroke", async () => {
  vi.useFakeTimers()
  vi.mocked(fetchAPI).mockResolvedValue({ items: [] })
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const view = (holder: string) => (
    <QueryClientProvider client={client}>
      <ReadingJudgements caseId="c1" statementId="k1" revision="r1" currency="USD" readingRows={[]} reviewRows={[]}
        fileId="f1" holder={holder} />
    </QueryClientProvider>
  )
  const { rerender } = render(view("E"))
  await act(async () => { await vi.advanceTimersByTimeAsync(10) })
  rerender(view("ER"))
  rerender(view("ERICA HOPPER"))
  await act(async () => { await vi.advanceTimersByTimeAsync(1000) })
  const holders = vi.mocked(fetchAPI).mock.calls.map(([, options]) => (options as { body: { holder?: string } }).body.holder)
  expect(holders).toEqual(["E", "ERICA HOPPER"])
})

// Alex's call (OPDMD66, STATEMENTS 5630.pdf): a damaged cell, Check first, before import.
const scanMark = {
  rule_id: "L9.scan_amount_marks",
  rule_label: "Scan mark read past",
  rule_source: "fin-queue L9",
  subject_type: "transaction",
  subject_id: "6:1:12",
  row_id: "6:1:12",
  strength: "proved",
  summary: "2024-01-22 credit 2,539.30: the amount on page 6 is printed '2,539.30?' in the scan; the space or mark is read past, and the printed balances agree with the value read.",
  target_key: "amount",
  category: "amount",
  category_label: "Amount read past damage",
  priority: 1,
  priority_label: "Check first",
  page: 6,
}

function preview(actions: Parameters<typeof ReadingJudgements>[0]["actions"]) {
  vi.mocked(fetchAPI).mockReset()
  vi.mocked(fetchAPI).mockResolvedValue({ items: [scanMark] })
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <ReadingJudgements caseId="c1" statementId="k1" revision="r1" currency="USD" readingRows={[]} reviewRows={[]}
        actions={actions} />
    </QueryClientProvider>
  )
}

function actionsWith(over: Partial<NonNullable<Parameters<typeof ReadingJudgements>[0]["actions"]>> = {}) {
  return { canEdit: true, checks: [], onCheck: vi.fn(), canCorrect: () => true, onCorrect: vi.fn(), onShow: vi.fn(), ...over }
}

it("offers Looks right, Correct this and the page on each call before import, and prompts to look first", async () => {
  const actions = actionsWith()
  preview(actions)
  // Check first opens the panel by itself and says what to do, in words.
  expect(await screen.findByText("Look at this value on the page before you import.")).toBeVisible()
  expect(screen.getByRole("button", { name: /1 to check first/ })).toHaveAttribute("aria-expanded", "true")
  expect(screen.getByText(/None of them stops the import/)).toBeVisible()
  expect(screen.queryByText(/nothing is held for them/)).toBeNull()
  fireEvent.click(screen.getByRole("button", { name: "Show on page 6" }))
  expect(actions.onShow).toHaveBeenCalledWith(expect.objectContaining({ row_id: "6:1:12", page: 6 }))
  fireEvent.click(screen.getByRole("button", { name: "Correct this" }))
  expect(actions.onCorrect).toHaveBeenCalledWith(expect.objectContaining({ row_id: "6:1:12", target_key: "amount" }))
  fireEvent.click(screen.getByRole("button", { name: /Looks right/ }))
  expect(actions.onCheck).toHaveBeenCalledWith(expect.objectContaining({ rule_id: "L9.scan_amount_marks" }), true)
})

it("shows a call already marked Looks right as kept with the review, with who checked it, and can undo it", async () => {
  const actions = actionsWith({
    checks: [{ rule_id: "L9.scan_amount_marks", row_id: "6:1:12", target_key: "amount", checked_at: "2026-11-12T20:00:00Z",
      checked_by: { name: "Alex" } }],
  })
  preview(actions)
  expect(await screen.findByText(/Looks right · Alex\. Recorded when the statement is imported\./)).toBeVisible()
  expect(screen.queryByText("Look at this value on the page before you import.")).toBeNull()
  expect(screen.getByRole("button", { name: /1 marked Looks right/ })).toBeVisible()
  fireEvent.click(screen.getByRole("button", { name: "Undo" }))
  expect(actions.onCheck).toHaveBeenCalledWith(expect.objectContaining({ target_key: "amount" }), false)
})

it("shows the actions to a person who can only view, disabled, and says why", async () => {
  preview(actionsWith({ canEdit: false }))
  expect(await screen.findByRole("button", { name: /Looks right/ })).toBeDisabled()
  expect(screen.getByRole("button", { name: "Correct this" })).toBeDisabled()
  expect(screen.getByRole("button", { name: "Show on page 6" })).toBeEnabled()
  expect(screen.getByText("You can view this case. Checking a call needs edit access.")).toBeVisible()
})
