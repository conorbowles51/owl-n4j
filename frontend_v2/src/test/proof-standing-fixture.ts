import type { ProofStandingResponse } from "@/features/financial/api"

export function proofStanding(caseId = "case-1"): ProofStandingResponse {
  return {
    case_id: caseId,
    documents: 5,
    transactions: 9,
    documents_requiring_adjudication: 2,
    transactions_requiring_adjudication: 4,
    counted_classes: ["p0", "p1", "p2"],
    classes: [
      {
        proof_class: "p0",
        documents: 0,
        transactions: 0,
        admits_automatically: true,
        requires_adjudication: false,
        may_produce_ledger_rows: true,
        counts_toward_totals: true,
      },
      {
        proof_class: "p1",
        documents: 1,
        transactions: 2,
        admits_automatically: true,
        requires_adjudication: false,
        may_produce_ledger_rows: true,
        counts_toward_totals: true,
      },
      {
        proof_class: "p2",
        documents: 1,
        transactions: 3,
        admits_automatically: true,
        requires_adjudication: false,
        may_produce_ledger_rows: true,
        counts_toward_totals: true,
      },
      {
        proof_class: "p3",
        documents: 2,
        transactions: 4,
        admits_automatically: false,
        requires_adjudication: true,
        may_produce_ledger_rows: true,
        counts_toward_totals: false,
      },
      {
        proof_class: "p4",
        documents: 1,
        transactions: 0,
        admits_automatically: false,
        requires_adjudication: false,
        may_produce_ledger_rows: false,
        counts_toward_totals: false,
      },
    ],
  }
}
