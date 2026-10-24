import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { beforeEach, expect, it, vi } from "vitest"
import { fetchAPI } from "@/lib/api-client"
import { QueueProposalGroups } from "./QueueProposalGroups"

vi.mock("@/lib/api-client", () => ({ fetchAPI: vi.fn() }))

const group = {
  id: "g".repeat(64), field: "currency", value: "MXN", basis: "case_default", label: "the case's usual currency",
  account: "1234", institution: "Bank", statements: 3, entry_ids: ["a", "b", "c"],
}

beforeEach(() => vi.mocked(fetchAPI).mockReset())

it("confirms one account's value for all its statements in one click", async () => {
  vi.mocked(fetchAPI).mockResolvedValue({ group_id: group.id, field: "currency", value: "MXN", statements: 3, saved: 3, failed: 0 } as never)
  const onDone = vi.fn()
  render(<QueueProposalGroups caseId="case" groups={[group]} fileIds={[]} onDone={onDone} />)
  fireEvent.click(screen.getByRole("button", { name: "Confirm for all 3" }))
  await waitFor(() => expect(onDone).toHaveBeenCalledWith("Currency MXN saved on 3 of 3 statements"))
  expect(vi.mocked(fetchAPI).mock.calls[0][0]).toContain("/review/proposal-groups/confirm?case_id=case")
})

it("shows nothing without groups", () => {
  const { container } = render(<QueueProposalGroups caseId="case" groups={[]} fileIds={[]} onDone={vi.fn()} />)
  expect(container.innerHTML).toBe("")
})

it("says why a confirmation failed", async () => {
  const send = vi.fn().mockRejectedValue(new Error("These statements changed since the proposal was shown. Reload the queue."))
  const onDone = vi.fn()
  render(<QueueProposalGroups caseId="case" groups={[group]} fileIds={[]} onDone={onDone} send={send} />)
  fireEvent.click(screen.getByRole("button", { name: "Confirm for all 3" }))
  expect(await screen.findByText(/changed since the proposal was shown/)).toBeTruthy()
  expect(onDone).not.toHaveBeenCalled()
})
