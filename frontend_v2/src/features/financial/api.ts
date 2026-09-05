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

/*
 * What produced the ledger, and what failed trying.
 *
 * Every row above carries a non-null `ingestion_run_id`, so the ledger has
 * always been able to say which attempt produced a transaction. `/runs` is the
 * opposite direction: what one attempt did, whether it finished, and what
 * stopped it if it did not.
 *
 * **The default population is the reverse of the ledger's.** `/ledger` defaults
 * to `admitted`, because that is the population every total is filtered to.
 * `/runs` defaults to *every* status, `failed` and `aborted` included, because
 * the failures are the reason to look. A list that hid them would answer "what
 * worked" while appearing to answer "what happened".
 */

/** Mirrors `IngestionRunStatus` in `backend/postgres/models/enums.py`. */
export const INGESTION_RUN_STATUSES = [
  "pending",
  "running",
  "completed",
  "failed",
  "aborted",
] as const
export type IngestionRunStatus = (typeof INGESTION_RUN_STATUSES)[number]

/**
 * One ingestion run, exactly as `RunView.to_json` in
 * `backend/services/financial/run_query.py` emits it.
 *
 * `status` is typed `string` rather than the union above for the same reason
 * the ledger's vocabulary fields are: a backend one version ahead can send a
 * member this build has never heard of, and a union would let it through while
 * claiming it had been checked. `run-format.ts` narrows it at runtime.
 */
export interface IngestionRun {
  key: string
  case_id: string
  /** One of `INGESTION_RUN_STATUSES`, narrowed rather than trusted. */
  status: string
  code_version: string | null
  ruleset_version: string | null
  /** Whatever the run was configured with. Shape is the run's, not this file's. */
  config: Record<string, unknown>
  /**
   * Nulls when the account is deleted. `started_by_email` is recorded beside it
   * precisely so that who started a run survives that, so prefer the email.
   */
  started_by_user_id: string | null
  started_by_email: string | null
  started_at: string | null
  /** Null while the run is still open, and on a run that never closed. */
  completed_at: string | null
  /**
   * What the run recorded about itself when it ended. These three are never
   * recomputed against the ledger as it stands now, and must not be reconciled
   * against it on this side either: adjudication moves rows after a run ends,
   * so a later count answers a different question than the one asked here.
   */
  documents_seen: number
  transactions_admitted: number
  transactions_quarantined: number
  error: string | null
  notes: string | null
}

/**
 * Every field the runs read emits, as a value rather than a type, for the same
 * reason `LEDGER_TRANSACTION_FIELDS` exists: `api.runs.test.ts` holds this list
 * up against `RunView.to_json` and requires the two to be the same set.
 */
export const INGESTION_RUN_FIELDS: readonly (keyof IngestionRun)[] = [
  "key",
  "case_id",
  "status",
  "code_version",
  "ruleset_version",
  "config",
  "started_by_user_id",
  "started_by_email",
  "started_at",
  "completed_at",
  "documents_seen",
  "transactions_admitted",
  "transactions_quarantined",
  "error",
  "notes",
]

export interface IngestionRunsResponse {
  case_id: string
  runs: IngestionRun[]
  total: number
}

/*
 * Getting rows into the ledger.
 *
 * Two endpoints reading the same file: `/precheck` says what it holds and
 * stores nothing, `/ingest` does that reading again and keeps it. They share a
 * parser on purpose, so a precheck that promised one thing and an ingest that
 * did another is not a state this pair can reach.
 *
 * Neither has a success flag and an error flag. Both answer with a single word
 * in `outcome`, and nearly every value of it arrives as a 200 because it is a
 * fact about the evidence rather than a fault: a file that will not parse, a
 * row naming an account the document never introduced, a period contradicting
 * one already stored. Those belong on the screen beside the files that went
 * in, not in the browser's error path. Only three become statuses -- 404 for a
 * file this case cannot see, 500 for a write that failed for a reason that is
 * not about the evidence, 400 for a century window that is not a window.
 *
 * The vocabularies are arrays for the same reason the ledger's are:
 * `ingest-format.ts` narrows a word this build has never heard of rather than
 * rendering it raw or crashing on it. `outcome` is therefore typed `string` on
 * both wire shapes below, because a union there would be this file claiming to
 * have checked something it has not.
 */

/** Mirrors `PrecheckOutcome` in `services/financial/native_precheck.py`. */
export const PRECHECK_OUTCOMES = [
  "readable",
  "unrecognised",
  "ambiguous",
  "out_of_window",
  "unattributable",
  "unreadable",
  "not_found",
] as const
export type PrecheckOutcome = (typeof PRECHECK_OUTCOMES)[number]

/**
 * Mirrors `IngestOutcome` in `services/financial/native_ingest_file.py`.
 *
 * Six of these are spelled the same as a `PrecheckOutcome` and mean the same
 * thing; the backend maps them across in `READING_OUTCOMES`. `readable` has no
 * counterpart here on purpose: once the rows are written the word is `stored`.
 * The three that precheck cannot reach -- `already_ingested`,
 * `contradictory_period`, `refused` -- are each decided against rows already in
 * the ledger rather than against the file, which is why a clean precheck is not
 * a promise that the ingest will store.
 */
export const INGEST_OUTCOMES = [
  "stored",
  "already_ingested",
  "not_found",
  "unrecognised",
  "ambiguous",
  "out_of_window",
  "unreadable",
  "undescribable",
  "unattributable",
  "contradictory_period",
  "refused",
  "write_failed",
] as const
export type IngestOutcome = (typeof INGEST_OUTCOMES)[number]

/** A balance the file printed, or a record that it printed none. */
export interface PrecheckBalance {
  source: string
  /**
   * Null with `source: "absent"` means the file stated no balance. It does not
   * mean zero, and must never be rendered as one.
   */
  amount_minor: number | null
  currency: string | null
}

export interface PrecheckPeriod {
  currency: string | null
  start: string | null
  end: string | null
  start_source: string
  end_source: string
  opening: PrecheckBalance
  closing: PrecheckBalance
}

export interface PrecheckAccount {
  account_key: string | null
  /**
   * Whether the rows could be attributed to an account the document
   * introduced. False does not mean no account number was printed --
   * `identifier_as_printed` sits beside it for exactly that case.
   */
  identified: boolean
  row_count: number
  institution_name: string | null
  identifier_as_printed: string | null
  account_type: string | null
  holder_name: string | null
  currency: string | null
  iban: string | null
  bic: string | null
  routing_number: string | null
  /** Null for every NACHA account, which is not a gap in the reading. */
  period: PrecheckPeriod | null
}

export interface PrecheckSkippedRow {
  row_index: number
  reason: string
}

/** The shape of `FilePrecheck.as_dict()`. */
export interface FilePrecheck {
  file_id: string
  file_name: string | null
  /** One of `PRECHECK_OUTCOMES`, narrowed rather than trusted. */
  outcome: string
  would_ingest: boolean
  reason: string | null
  detected_format: string | null
  parser_name: string | null
  parser_version: string | null
  extraction_layer: number | null
  source_shape: string | null
  reconciliation_status: string | null
  proof_class: string | null
  admissibility_reservations: string[]
  row_count: number | null
  parsed_row_count: number | null
  skipped: PrecheckSkippedRow[]
  earliest_ordering_date: string | null
  latest_ordering_date: string | null
  accounts: PrecheckAccount[]
  unattributed_keys: (string | null)[]
  unattributed_row_count: number
}

/** The shape of `FileIngestion.as_dict()`. */
export interface FileIngestion {
  file_id: string
  file_name: string | null
  /** One of `INGEST_OUTCOMES`, narrowed rather than trusted. */
  outcome: string
  stored: boolean
  reason: string | null
  run_id: string | null
  document_id: string | null
  detected_format: string | null
  account_ids: string[]
  period_ids: string[]
  transactions_stored: number
  unlinked_rows: number
  adjudication_id: string | null
}

/**
 * The window both endpoints require, and the currency neither will guess.
 *
 * `windowStart`/`windowEnd` are not optional and have no default. Three of the
 * four native formats print two-digit years and none carries the century, so
 * without a stated period the year cannot be resolved. A default would decide
 * which decade a statement belongs to silently, in the one place the document
 * itself is no help.
 *
 * `defaultCurrency` is asked for rather than inferred because a wrong guess
 * produces amounts that look right.
 */
export interface IngestWindowParams {
  caseId: string
  fileId: string
  /** `YYYY-MM-DD`. Earliest date this matter's evidence may fall in. */
  windowStart: string
  /** `YYYY-MM-DD`. Latest date this matter's evidence may fall in. */
  windowEnd: string
  defaultCurrency?: string
}

function ingestWindowQuery(params: IngestWindowParams): URLSearchParams {
  const qs = new URLSearchParams({
    case_id: params.caseId,
    file_id: params.fileId,
    window_start: params.windowStart,
    window_end: params.windowEnd,
  })
  if (params.defaultCurrency) qs.set("default_currency", params.defaultCurrency)
  return qs
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

  /**
   * The ingestion runs for a case, newest first.
   *
   * `status` left unset is every status, which is the endpoint's own default
   * and the opposite of the ledger's. This function therefore sends no default
   * of its own: a default here could drift from the backend's and quietly start
   * hiding the failed runs this read exists to surface.
   *
   * `limit` is refused by the backend below 1, because a limit of zero returns
   * nothing while looking like a request for something.
   */
  getIngestionRuns: (params: {
    caseId: string
    status?: IngestionRunStatus
    limit?: number
  }) => {
    const qs = new URLSearchParams({ case_id: params.caseId })
    if (params.status) qs.set("status", params.status)
    if (params.limit !== undefined) qs.set("limit", String(params.limit))
    return fetchAPI<IngestionRunsResponse>(`/api/financial/runs?${qs}`)
  },

  /**
   * What one native bank file says it holds. Stores nothing.
   *
   * A POST because it takes a file and does work, not because it changes
   * anything; the backend gates it on being able to see the case rather than
   * on being able to add to it, and resolves the method the same way.
   *
   * A `readable` answer here is the strongest thing that can be said before a
   * write is attempted, and it is still not a promise. Three of the ingest
   * outcomes are decided against rows already stored and no amount of reading
   * this file would find them.
   */
  precheckFile: (params: IngestWindowParams) =>
    fetchAPI<FilePrecheck>(`/api/financial/precheck?${ingestWindowQuery(params)}`, {
      method: "POST",
    }),

  /**
   * Read the file again and keep it, under a recorded ingestion run.
   *
   * `documentType` overrides the format's own name on the stored document.
   * `institutionName` names the bank where the file does not; it is recorded as
   * given and never inferred from an account number, because an account number
   * that resembles a bank's range is not evidence of which bank issued it.
   */
  ingestFile: (
    params: IngestWindowParams & {
      documentType?: string
      institutionName?: string
    }
  ) => {
    const qs = ingestWindowQuery(params)
    if (params.documentType) qs.set("document_type", params.documentType)
    if (params.institutionName) qs.set("institution_name", params.institutionName)
    return fetchAPI<FileIngestion>(`/api/financial/ingest?${qs}`, { method: "POST" })
  },
}
