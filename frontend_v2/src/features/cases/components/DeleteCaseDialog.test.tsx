import { fireEvent, render, screen } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import type { Case } from "@/types/case.types"
import { DeleteCaseDialog } from "./DeleteCaseDialog"
import { describeCaseCounts } from "../api"

const hooks = vi.hoisted(() => ({
  mutate: vi.fn(),
  preview: {
    isLoading: false,
    isError: false,
    data: {
      case_id: "case-1",
      title: "Operation Lantern",
      restorable_days: 30,
      holds: { evidence_files: 12, financial_transactions: 480, financial_accounts: 8, adjudications: 0 },
    },
  },
}))

vi.mock("../hooks/use-cases", () => ({
  useDeleteCase: () => ({ mutate: hooks.mutate, isPending: false, isError: false, reset: vi.fn() }),
  useCaseDeletePreview: () => hooks.preview,
}))

const lantern = {
  id: "case-1",
  title: "Operation Lantern",
  description: null,
  status: "active",
  created_by_user_id: "user-1",
  owner_user_id: "user-1",
  created_at: "2026-07-01T09:00:00Z",
  updated_at: "2026-07-16T10:30:00Z",
  owner_name: "Owner",
  user_role: "owner",
  is_owner: true,
  archived: false,
  next_deadline_date: null,
  next_deadline_name: null,
} as unknown as Case

describe("DeleteCaseDialog", () => {
  beforeEach(() => hooks.mutate.mockReset())

  it("says what the case holds and that it can be restored for 30 days", () => {
    render(<DeleteCaseDialog open onOpenChange={() => {}} caseToDelete={lantern} />)
    const summary = screen.getByTestId("delete-case-summary").textContent ?? ""
    expect(summary).toContain("12 evidence files")
    expect(summary).toContain("8 accounts")
    expect(summary).toContain("480 ledger rows")
    expect(summary).not.toContain("review decisions")
    expect(summary).toContain("for 30 days")
    expect(summary).not.toMatch(/permanent|irreversibl/i)
  })

  it("deletes only once the title is typed exactly, and sends the typed title", () => {
    render(<DeleteCaseDialog open onOpenChange={() => {}} caseToDelete={lantern} />)
    const button = screen.getByRole("button", { name: "Move to Deleted items" })
    expect(button).toBeDisabled()
    fireEvent.change(screen.getByLabelText("Case title to confirm"), { target: { value: "Operation Lanter" } })
    expect(button).toBeDisabled()
    fireEvent.click(button)
    expect(hooks.mutate).not.toHaveBeenCalled()
    fireEvent.change(screen.getByLabelText("Case title to confirm"), { target: { value: "Operation Lantern" } })
    expect(button).not.toBeDisabled()
    fireEvent.click(button)
    expect(hooks.mutate).toHaveBeenCalledTimes(1)
    expect(hooks.mutate.mock.calls[0][0]).toEqual({ caseId: "case-1", confirmTitle: "Operation Lantern" })
  })

  it("with Deleted items switched off (live) says the delete is permanent and never mentions Deleted items", () => {
    const on = hooks.preview.data
    hooks.preview = { ...hooks.preview, data: { ...on, restorable_days: null } as unknown as typeof on }
    try {
      render(<DeleteCaseDialog open onOpenChange={() => {}} caseToDelete={lantern} />)
      const summary = screen.getByTestId("delete-case-summary").textContent ?? ""
      expect(summary).toContain("480 ledger rows")
      expect(summary).toMatch(/permanent/)
      expect(document.body.textContent ?? "").not.toMatch(/Deleted items|restore|30 days/i)
      const button = screen.getByRole("button", { name: "Delete Case" })
      expect(button).toBeDisabled()
      fireEvent.change(screen.getByLabelText("Case title to confirm"), { target: { value: "Operation Lantern" } })
      fireEvent.click(button)
      expect(hooks.mutate).toHaveBeenCalledWith(
        { caseId: "case-1", confirmTitle: "Operation Lantern" },
        expect.anything()
      )
    } finally {
      hooks.preview = { ...hooks.preview, data: on }
    }
  })

  it("counts one of a kind in the singular", () => {
    expect(describeCaseCounts({ evidence_files: 1, case_memberships: 1, workspace_entries: 7, adjudications: 0 })).toEqual([
      "1 evidence file",
      "7 notes and workspace entries",
      "1 member",
    ])
  })
})
