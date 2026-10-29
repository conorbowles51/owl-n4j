import { describe, expect, it } from "vitest"
import { statementDuplicateDisposition } from "./statement-duplicate"
import { statementImportStates } from "../hooks/use-statement-register"
import { fileCopyLine } from "./statement-copies"

const revision = "a".repeat(64)
// The decision the server saves when a statement is a copy of one already in the
// ledger (backend/services/financial/saved_copies.py, basis "saved_ledger_copy").
const savedLedgerCopy = {
  policy: "statement-duplicates-v1",
  reading_revision: revision,
  revision: "b".repeat(64),
  status: "ignored",
  label: "Copy of a saved statement",
  reason: "Same account, period, balances and payments as a saved statement.",
  current: true,
  matched_fields: ["account", "period", "opening", "closing", "payments"],
  basis: "saved_ledger_copy",
  retained: {
    evidence_file_id: "6f1c2a52-6a43-4d8e-9b54-0a4f1f2a1b10",
    statement_id: "c".repeat(64),
    source_document_id: "0d2b1e7c-1c55-4b8f-8a9d-6b1f6a2c3d40",
    filename: "BBVA 2019-03.pdf",
    page_number: 1,
  },
  saved_ledger_match: { statement_period_id: "p1", payments: 12 },
}

describe("statement copy decisions", () => {
  it("reads a copy recognised by any server reason, such as a saved ledger copy", () => {
    for (const basis of [
      "saved_ledger_copy",
      "part_of_saved_statement",
      "printed_balances_of_saved_statement",
      "a_reason_added_later",
    ]) {
      const parsed = statementDuplicateDisposition.parse({ ...savedLedgerCopy, basis })
      expect(parsed.basis).toBe(basis)
    }
  })

  it("keeps the case's file register readable when a file holds such a copy", () => {
    const register = statementImportStates.parse({
      case_id: "d5b330d1-b3fe-4b03-8539-98d9cc3115e0",
      truncated: false,
      files: [
        {
          evidence_file_id: "1e0f7c55-2f1a-4c3e-8f0e-3a9b2c1d0e11",
          current_transactions: 0,
          ignored_periods: 1,
          prepared_periods: 1,
          duplicate_dispositions: [{ statement_id: revision, currency: "MXN", decision: savedLedgerCopy }],
          periods: [],
        },
      ],
    })
    expect(register.files[0].duplicate_dispositions[0].decision.basis).toBe("saved_ledger_copy")
    expect(fileCopyLine(register.files[0])).toContain("BBVA 2019-03.pdf")
  })
})
