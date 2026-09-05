import { fetchAPI } from "@/lib/api-client"

export interface TransactionEntity {
  key: string | null
  name: string | null
}

export type FinancialDatasetMode = "transactions" | "intelligence"
export type FinancialViewMode = "transaction" | "intelligence"
export type FinancialRecordKind =
  | "transaction"
  | "invoice"
  | "payment_instruction"
  | "balance"
  | "asset_value"
  | "fraud_total"
  | "allegation"
  | "summary_metric"
  | "other"
export type EvidenceStrength = "documentary" | "derived" | "narrative" | "unknown"
export type EvidenceSourceType =
  | "bank_statement"
  | "invoice"
  | "receipt"
  | "wire"
  | "card_statement"
  | "ledger"
  | "official_report"
  | "email"
  | "interview"
  | "other"

interface BaseFinancialRecord {
  key: string
  date?: string | null
  time?: string
  name?: string
  type?: string
  amount: number
  currency?: string
  category?: string
  summary?: string
  from_entity: TransactionEntity
  to_entity: TransactionEntity
  has_manual_from?: boolean
  has_manual_to?: boolean
  is_parent?: boolean
  parent_transaction_key?: string | null
  amount_corrected?: boolean
  original_amount?: number | null
  correction_reason?: string | null
  purpose?: string
  counterparty_details?: string
  notes?: string
  financial_record_kind: FinancialRecordKind
  financial_view_mode: FinancialViewMode
  is_financial_event: boolean
  evidence_strength?: EvidenceStrength | null
  evidence_source_type?: EvidenceSourceType | null
  source_document_id?: string | null
  source_filename?: string | null
  source_page?: number | null
  source_excerpt?: string | null
  extraction_confidence?: number | null
  /**
   * The raw value of `provenance["locator"]` (Neo4j: attached by
   * `attach_transaction_locators` on read; Postgres ledger: written at
   * ingestion). Unparsed on purpose — `readLocator` in
   * `features/financial/lib/locator.ts` is the one place that reads it, so
   * this side of the contract never guesses at a shape the backend didn't
   * commit to.
   */
  locator?: unknown
}

export interface TransactionRecord extends BaseFinancialRecord {
  financial_view_mode: "transaction"
  is_evidence_backed_transaction: boolean
}

export interface FinancialIntelligenceRecord extends BaseFinancialRecord {
  financial_view_mode: "intelligence"
  is_evidence_backed_transaction: false
}

export type Transaction = TransactionRecord | FinancialIntelligenceRecord

export interface TransactionsResponse {
  transactions: Transaction[]
  total: number
  dataset_mode: FinancialDatasetMode
  uses_legacy_financial_model: boolean
}

export interface FinancialSummary {
  total_inflows?: number
  total_outflows?: number
  net_flow: number
  transaction_count: number
  total_volume?: number
  avg_amount?: number
  max_amount?: number
  dataset_mode: FinancialDatasetMode
  uses_legacy_financial_model: boolean
}

export interface FinancialCategory {
  name: string
  color: string
}

export interface AmountCorrection {
  node_key: string
  new_amount: number
  correction_reason: string
}

export interface VolumeDataPoint {
  date: string
  category: string
  total_amount: number
  count: number
}

export interface VolumeResponse {
  data: VolumeDataPoint[]
  dataset_mode: FinancialDatasetMode
  uses_legacy_financial_model: boolean
}

/*
 * The relational ledger.
 *
 * Everything above this line describes `/api/financial`, which reads the Neo4j
 * graph. `/api/financial/ledger` reads the other store: the Postgres ledger
 * tables that ingestion writes into. The two hold a mirror of the same facts,
 * but only the relational rows carry the provenance and admissibility columns
 * below, so this is a separate shape rather than a variant of `Transaction`.
 *
 * The closed vocabularies are declared here as arrays rather than as bare
 * unions so `ledger-format.ts` can narrow a value it does not recognise. Each
 * one mirrors an enum in `backend/postgres/models/enums.py`, and
 * `api.ledger.test.ts` reads that file to prove the two languages still agree.
 */

export const LEDGER_STATUSES = [
  "admitted",
  "quarantined",
  "superseded",
  "rejected",
] as const
export type LedgerStatus = (typeof LEDGER_STATUSES)[number]

export const PROOF_CLASSES = ["p0", "p1", "p2", "p3", "p4"] as const
export type ProofClass = (typeof PROOF_CLASSES)[number]

export const TRANSACTION_DIRECTIONS = ["credit", "debit"] as const
export type TransactionDirection = (typeof TRANSACTION_DIRECTIONS)[number]

export const DATE_SOURCES = [
  "transaction",
  "posted",
  "value",
  "effective",
] as const
export type DateSource = (typeof DATE_SOURCES)[number]

export const QUARANTINE_REASONS = [
  "balance_break",
  "unreadable_row",
  "currency_mismatch",
  "unexplained_delta",
  "adjudicated",
] as const
export type QuarantineReason = (typeof QUARANTINE_REASONS)[number]

/**
 * One row of the relational ledger, exactly as `TransactionView.to_json` in
 * `backend/services/financial/transaction_query.py` emits it.
 *
 * The closed-vocabulary fields are typed `string` and `number` rather than as
 * the unions above, on purpose. A backend one version ahead of this build can
 * legitimately send a member this build has never heard of, and a union type
 * would let that value through to the screen while claiming it had been
 * checked. Narrowing is a runtime job: `ledger-format.ts` does it, and every
 * one of these fields reaches a component through that module.
 */
export interface LedgerTransaction {
  key: string
  case_id: string
  account_id: string
  source_document_id: string
  ingestion_run_id: string
  statement_period_id: string | null
  ref_id: string
  row_index: number
  /**
   * Minor units, always a magnitude and never signed: the ledger keeps the
   * sign in `direction`. Never divide this by 100 — how many minor units make
   * a major unit depends on the currency, and `formatLedgerAmount` in
   * `ledger-format.ts` is the one place that knows it.
   */
  amount_minor: number
  currency: string
  direction: string
  running_balance_minor: number | null
  transaction_date: string | null
  posted_date: string | null
  value_date: string | null
  effective_date: string | null
  /**
   * The date the ledger orders and reconciles by, chosen from up to four
   * printed dates. `ordering_date_source` records which one it came from.
   */
  ordering_date: string
  ordering_date_source: string
  description: string | null
  counterparty_raw: string | null
  transaction_type: string | null
  bank_reference: string | null
  proof_class: string
  extraction_layer: number
  ledger_status: string
  quarantine_reason: string | null
  superseded_by_id: string | null
  /**
   * The raw value of `provenance["locator"]`, unparsed for the same reason
   * `BaseFinancialRecord.locator` is: `readLocator` in `lib/locator.ts` is the
   * only place that reads it.
   */
  locator?: unknown
}

/**
 * Every field the ledger read emits, as a value rather than a type.
 *
 * An interface vanishes at runtime, so on its own it can only describe what
 * this build believes the backend sends. This list is the same contract in a
 * form a test can hold up against the Python: `api.ledger.test.ts` reads
 * `TransactionView.to_json` and requires the two to be the same set. Without
 * it, a column added to the ledger read would arrive on this screen and be
 * dropped in silence, which on a financial row is the difference between a
 * figure that can be traced and one that cannot.
 *
 * Typed `keyof LedgerTransaction`, so a name here the interface does not
 * declare fails to compile; the test closes the other direction.
 */
export const LEDGER_TRANSACTION_FIELDS: readonly (keyof LedgerTransaction)[] = [
  "key",
  "case_id",
  "account_id",
  "source_document_id",
  "ingestion_run_id",
  "statement_period_id",
  "ref_id",
  "row_index",
  "amount_minor",
  "currency",
  "direction",
  "running_balance_minor",
  "transaction_date",
  "posted_date",
  "value_date",
  "effective_date",
  "ordering_date",
  "ordering_date_source",
  "description",
  "counterparty_raw",
  "transaction_type",
  "bank_reference",
  "proof_class",
  "extraction_layer",
  "ledger_status",
  "quarantine_reason",
  "superseded_by_id",
  "locator",
]

export interface LedgerResponse {
  case_id: string
  transactions: LedgerTransaction[]
  total: number
}

export const financialAPI = {
  getTransactions: (params: {
    caseId: string
    mode?: FinancialDatasetMode
    types?: string[]
    startDate?: string
    endDate?: string
    categories?: string[]
  }) => {
    const qs = new URLSearchParams({ case_id: params.caseId })
    qs.set("mode", params.mode || "transactions")
    if (params.types?.length) qs.set("types", params.types.join(","))
    if (params.startDate) qs.set("start_date", params.startDate)
    if (params.endDate) qs.set("end_date", params.endDate)
    if (params.categories?.length) qs.set("categories", params.categories.join(","))
    return fetchAPI<TransactionsResponse>(`/api/financial?${qs}`)
  },

  getSummary: (caseId: string, mode: FinancialDatasetMode = "transactions") =>
    fetchAPI<FinancialSummary>(`/api/financial/summary?case_id=${caseId}&mode=${mode}`),

  getVolume: (caseId: string, mode: FinancialDatasetMode = "transactions") =>
    fetchAPI<VolumeResponse>(`/api/financial/volume?case_id=${caseId}&mode=${mode}`),

  categorize: (nodeKey: string, category: string, caseId: string) =>
    fetchAPI<void>(`/api/financial/categorize/${encodeURIComponent(nodeKey)}`, {
      method: "PUT",
      body: { category, case_id: caseId },
    }),

  batchCategorize: (nodeKeys: string[], category: string, caseId: string) =>
    fetchAPI<void>("/api/financial/batch-categorize", {
      method: "PUT",
      body: { node_keys: nodeKeys, category, case_id: caseId },
    }),

  setFromTo: (
    nodeKey: string,
    params: {
      caseId: string
      fromKey?: string
      fromName?: string
      toKey?: string
      toName?: string
    }
  ) =>
    fetchAPI<void>(`/api/financial/from-to/${encodeURIComponent(nodeKey)}`, {
      method: "PUT",
      body: {
        case_id: params.caseId,
        from_key: params.fromKey,
        from_name: params.fromName,
        to_key: params.toKey,
        to_name: params.toName,
      },
    }),

  batchSetFromTo: (
    nodeKeys: string[],
    params: {
      caseId: string
      fromKey?: string
      fromName?: string
      toKey?: string
      toName?: string
    }
  ) =>
    fetchAPI<void>("/api/financial/batch-from-to", {
      method: "PUT",
      body: {
        node_keys: nodeKeys,
        case_id: params.caseId,
        from_key: params.fromKey,
        from_name: params.fromName,
        to_key: params.toKey,
        to_name: params.toName,
      },
    }),

  updateDetails: (
    nodeKey: string,
    params: {
      caseId: string
      purpose?: string
      counterpartyDetails?: string
      notes?: string
    }
  ) =>
    fetchAPI<void>(`/api/financial/details/${encodeURIComponent(nodeKey)}`, {
      method: "PUT",
      body: {
        case_id: params.caseId,
        purpose: params.purpose,
        counterparty_details: params.counterpartyDetails,
        notes: params.notes,
      },
    }),

  getCategories: (caseId: string, mode: FinancialDatasetMode = "transactions") =>
    fetchAPI<{ categories: FinancialCategory[] }>(`/api/financial/categories?case_id=${caseId}&mode=${mode}`)
      .then((res) => res.categories),

  createCategory: (name: string, color: string, caseId: string) =>
    fetchAPI<FinancialCategory>("/api/financial/categories", {
      method: "POST",
      body: { name, color, case_id: caseId },
    }),

  updateAmount: (
    nodeKey: string,
    params: { caseId: string; newAmount: number; correctionReason: string }
  ) =>
    fetchAPI<void>(
      `/api/financial/transactions/${encodeURIComponent(nodeKey)}/amount`,
      {
        method: "PUT",
        body: {
          case_id: params.caseId,
          new_amount: params.newAmount,
          correction_reason: params.correctionReason,
        },
      }
    ),

  bulkCorrect: (caseId: string, corrections: AmountCorrection[]) =>
    fetchAPI<void>("/api/financial/transactions/bulk-correct", {
      method: "POST",
      body: { case_id: caseId, corrections },
    }),

  linkSubTransaction: (parentKey: string, childKey: string, caseId: string) =>
    fetchAPI<void>(
      `/api/financial/transactions/${encodeURIComponent(parentKey)}/sub-transactions`,
      {
        method: "POST",
        body: { case_id: caseId, child_key: childKey },
      }
    ),

  unlinkSubTransaction: (childKey: string, caseId: string) =>
    fetchAPI<void>(
      `/api/financial/transactions/${encodeURIComponent(childKey)}/parent?case_id=${caseId}`,
      { method: "DELETE" }
    ),

  getEntities: (caseId: string) =>
    fetchAPI<{ entities: TransactionEntity[] }>(`/api/financial/entities?case_id=${caseId}`)
      .then((res) => res.entities),

  getSubTransactions: (parentKey: string, caseId: string) =>
    fetchAPI<{ children: Transaction[]; count: number }>(
      `/api/financial/transactions/${encodeURIComponent(parentKey)}/sub-transactions?case_id=${caseId}`
    ).then((res) => res.children),

  /**
   * Rows from the relational ledger.
   *
   * `ledgerStatus` left unset is not "every row": the endpoint defaults to
   * `admitted`, the population every total in this ledger is filtered to.
   * Asking for quarantined or superseded rows is an explicit act here for the
   * same reason it is on the backend, so this function sends no default of its
   * own and lets the one the ledger already has stand.
   *
   * `startDate`/`endDate` bound `ordering_date` — the column the ledger orders
   * and reconciles by — not any of the four printed dates a row may carry.
   * Both are `YYYY-MM-DD`.
   *
   * `mode` has no meaning here. It selects between two Neo4j datasets on
   * `/api/financial`; this endpoint reads one relational table.
   */
  getLedgerTransactions: (params: {
    caseId: string
    accountId?: string
    ledgerStatus?: LedgerStatus
    startDate?: string
    endDate?: string
  }) => {
    const qs = new URLSearchParams({ case_id: params.caseId })
    if (params.accountId) qs.set("account_id", params.accountId)
    if (params.ledgerStatus) qs.set("ledger_status", params.ledgerStatus)
    if (params.startDate) qs.set("start_date", params.startDate)
    if (params.endDate) qs.set("end_date", params.endDate)
    return fetchAPI<LedgerResponse>(`/api/financial/ledger?${qs}`)
  },
}
