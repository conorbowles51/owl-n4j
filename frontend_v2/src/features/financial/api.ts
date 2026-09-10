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
  amount_minor: string | number
  currency: string
  direction: string
  running_balance_minor: string | number | null
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
  ordering_date_context?: "statement_end_ordering_only"
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

/*
 * Changing what a stored row counts as.
 *
 * The two sections above read the ledger and write to it from a file. This one
 * is neither: it changes the standing of a row already stored, months after the
 * file it came from was read. `backend/routers/financial_adjudication.py` is a
 * separate router for the same reason this is a separate section.
 *
 * The important thing about this endpoint is that almost nothing it can say is
 * an error. Only a missing row (404) and a failed write (500) leave the happy
 * path; a refusal comes back 200 carrying the refusal, so it can be shown
 * beside the row rather than thrown. `api.adjudication.test.ts` reads the
 * router and holds this build to that.
 */

export const ROW_ADJUDICATION_OUTCOMES = [
  "quarantined",
  "released",
  "unchanged",
  "not_found",
  "refused",
  "write_failed",
] as const
export type RowAdjudicationOutcome = (typeof ROW_ADJUDICATION_OUTCOMES)[number]

/**
 * The shape of `RowAdjudication.as_dict()`.
 *
 * `outcome`, `ledger_status` and `quarantine_reason` are typed `string` rather
 * than as the unions this file declares, for the reason `LedgerTransaction`
 * gives: a backend one version ahead can send a member this build has never
 * heard of, and a union type would let it through while claiming it had been
 * checked. `adjudication-format.ts` narrows them.
 */
export interface RowAdjudication {
  transaction_id: string
  /** One of `ROW_ADJUDICATION_OUTCOMES`, narrowed rather than trusted. */
  outcome: string
  /** True only for `quarantined` and `released`. Derived on the backend. */
  applied: boolean
  /**
   * Overloaded by outcome, and must not be presented as one thing.
   *
   * On `quarantined` it is the machine's own note about the rescue check, or
   * null when there was nothing to say. On `refused` and `unchanged` it is why
   * the writers would not act. On `not_found` and `write_failed` it never
   * reaches here as a field at all, because the router turns those two into
   * HTTP errors and this shape is what a 200 carries.
   */
  reason: string | null
  /** The row's status after the attempt. Absent when the row was not found. */
  ledger_status: string | null
  quarantine_reason: string | null
  /** Set only where a decision was actually appended to the log. */
  adjudication_id: string | null
  /**
   * Whether setting this row aside made its statement period balance.
   *
   * Three-valued on purpose, and the three values are not two. `true` means
   * the period was out and this row accounted for exactly the gap. `false`
   * means no gap was closed, which covers a period that already balanced, one
   * whose statement never printed the balances the check needs, and a row
   * belonging to no period. `null` means the question was asked and could not
   * be answered. Reporting that last case as `false` would claim something
   * that was never established.
   *
   * Null on every outcome except `quarantined`, and this response is the only
   * place the fact appears: it is deliberately not written to the log, because
   * a machine's observation must not be recorded as a person's finding. A
   * screen that drops it loses it.
   */
  rescues_period: boolean | null
}

/**
 * Every field an adjudication response carries, as a value rather than a type.
 *
 * The same contract as the interface, in a form `api.adjudication.test.ts` can
 * hold up against `RowAdjudication.as_dict()` in the Python. Typed
 * `keyof RowAdjudication`, so a name here the interface does not declare fails
 * to compile; the test closes the other direction.
 */
export const ROW_ADJUDICATION_FIELDS: readonly (keyof RowAdjudication)[] = [
  "transaction_id",
  "outcome",
  "applied",
  "reason",
  "ledger_status",
  "quarantine_reason",
  "adjudication_id",
  "rescues_period",
]

/**
 * What both adjudication calls need.
 *
 * `reason` is not optional and has no default, matching the backend, which
 * requires it on both routes. Setting a row aside takes it out of every sum,
 * search and money flow the case reports; a row set aside with nothing on the
 * record leaves a total lower than the evidence and no way to explain the
 * difference. Releasing one needs it for a reason the row itself cannot hold:
 * a released row must carry no quarantine reason, so the log is the only place
 * that can say why it was let back in.
 */
export interface RowAdjudicationParams {
  caseId: string
  transactionId: string
  reason: string
}

/*
 * Reading back what was decided.
 *
 * The section above writes to the adjudication log. This one reads it, and it
 * is the only thing that does. Every quarantine, release, supersession, purge
 * and machine reclassification a case has ever recorded is appended there, and
 * until `/api/financial/decisions` existed none of it could be got back out.
 *
 * Three things about this read shape the types below.
 *
 * **The page is bounded and says so.** Unlike `/ledger`, which returns every
 * matching row, this read is capped. It has to be: `reclassify_document` is
 * written by the reconciliation stage on every run, so the log grows without
 * anybody deciding anything. `total` counts every decision matching the same
 * filters and `truncated` says whether any were left off. Neither is optional
 * and neither may be dropped on the way to a screen, because a history that
 * quietly stops is worse than no history.
 *
 * **`by_machine` is the one derived field**, and it is the one that matters
 * most to get in front of a reader. The reconciliation stage decides under an
 * address at `.invalid`, which no person's account can hold, so the backend can
 * separate a machine's reclassification from a person's judgement exactly. It
 * does that separation once, on its side, rather than leaving every reader to
 * compare against a constant -- a reader that got it wrong would show software
 * moving a document as though an analyst had.
 *
 * **Adjacency is not sequence.** The order is newest first by `recorded_at`,
 * which is transaction-start time on the backend, so two decisions written in
 * one transaction share it exactly. Within one subject `subject_sequence` is
 * authoritative and the order respects it. Across subjects it says nothing, and
 * nothing built on this shape may present two neighbouring rows about different
 * subjects as having happened in the order shown.
 */

/** Mirrors `AdjudicationSubject` in `backend/postgres/models/enums.py`. */
export const ADJUDICATION_SUBJECTS = [
  "transaction",
  "statement_period",
  "source_document",
  "account",
  "evidence_file",
] as const
export type AdjudicationSubject = (typeof ADJUDICATION_SUBJECTS)[number]

/**
 * Mirrors `AdjudicationDecision` in `backend/postgres/models/enums.py`.
 *
 * Declared in the backend's own order, which groups the reversible pairs: a
 * supersession beside its restore, a quarantine beside its release. That
 * pairing is the point of the vocabulary -- the log appends the undo rather
 * than retracting the original -- so anything rendering these words should keep
 * the pairs together rather than sorting them alphabetically.
 */
export const ADJUDICATION_DECISIONS = [
  "supersede_duplicate",
  "restore_document",
  "purge_duplicate",
  "quarantine_row",
  "release_row",
  "explain_balance_failure",
  "reclassify_document",
  "admit_financial_document",
  "correct_transaction",
  "set_account_party",
] as const
export type AdjudicationDecision = (typeof ADJUDICATION_DECISIONS)[number]

/**
 * One recorded decision, exactly as `DecisionRecord.as_dict` in
 * `backend/services/financial/decision_log.py` emits it.
 *
 * `subject_type` and `decision` are typed `string` rather than as the unions
 * above, for the reason `LedgerTransaction` gives: a backend one version ahead
 * can send a member this build has never heard of, and a union would let it
 * through while claiming it had been checked. Narrowing is a runtime job.
 */
export interface DecisionRecord {
  id: string
  case_id: string
  /** One of `ADJUDICATION_SUBJECTS`, narrowed rather than trusted. */
  subject_type: string
  subject_id: string
  /**
   * 1 for the first decision about this subject, one more for each after. The
   * only order in this log that is authoritative; see the section comment on
   * what that means for a list spanning subjects.
   */
  subject_sequence: number
  /** One of `ADJUDICATION_DECISIONS`, narrowed rather than trusted. */
  decision: string
  reason: string
  /**
   * The subject's state either side of the decision, as stored. Shape is the
   * writer's, not this file's, and money in it is already in integer minor
   * units. `unknown` rather than a record type because nothing here knows what
   * a given decision chose to record.
   */
  before: unknown
  after: unknown
  /**
   * `actor_user_id` nulls when the account is deleted. The name and address are
   * recorded beside it precisely so that who decided survives that, which is
   * the whole reason an audit trail copies them rather than joining.
   */
  actor_name: string
  actor_email: string
  actor_user_id: string | null
  ingestion_run_id: string | null
  /** ISO 8601, or null on a row whose timestamp could not be read. */
  recorded_at: string | null
  /** Whether the reconciliation stage wrote this, rather than a person. */
  by_machine: boolean
}

/**
 * Every field a decision record carries, as a value rather than a type.
 *
 * The same contract as the interface, in a form `api.decisions.test.ts` can
 * hold up against the Python. Typed `keyof DecisionRecord`, so a name here the
 * interface does not declare fails to compile; the test closes the other
 * direction. A field added to the log and not listed here is not a compile
 * error on either side -- it is a fact about a decision that never reaches
 * anyone.
 */
export const DECISION_FIELDS: readonly (keyof DecisionRecord)[] = [
  "id",
  "case_id",
  "subject_type",
  "subject_id",
  "subject_sequence",
  "decision",
  "reason",
  "before",
  "after",
  "actor_name",
  "actor_email",
  "actor_user_id",
  "ingestion_run_id",
  "recorded_at",
  "by_machine",
]

/**
 * One page of a case's decision log.
 *
 * `limit` is the limit the backend *applied*, which is not always the one that
 * was asked for: a limit above the cap is capped and answered rather than
 * refused. Read the page size from here rather than from what was sent.
 */
export interface DecisionsResponse {
  case_id: string
  decisions: DecisionRecord[]
  /** Every decision matching the same filters, not the length of this page. */
  total: number
  limit: number
  offset: number
  /** Whether decisions matching this read were left off the page. */
  truncated: boolean
}

/**
 * What a read of the decision log may be narrowed by.
 *
 * `subjectId` may be given without `subjectType`. The pair is not unique in
 * principle, but the returned records each name their own subject type, and
 * the read is scoped to the case either way: a subject belonging to another
 * matter comes back empty rather than answered.
 */
export interface CaseDecisionsParams {
  caseId: string
  subjectType?: AdjudicationSubject
  subjectId?: string
  decision?: AdjudicationDecision
  limit?: number
  offset?: number
}

/*
 * Where a case's evidence stands by proof class.
 *
 * Proof class is computed from what the evidence is and whether its arithmetic
 * held. It is never set by hand, and nothing in this file or anywhere else in
 * the interface may offer a control that sets one: a class a person can raise
 * is an opinion, and the whole value of the label is that it is not.
 *
 * The counts and the permissions arrive together, and they must stay together
 * on the way to a screen. `p3` is a two-character string that says nothing on
 * its own, and the fact it names -- that this is the one class no ingestion run
 * admits by itself, so the material sits outside the verified ledger until a
 * person rules on it and that ruling is recorded -- is not recoverable from the
 * label. A count shown without its permissions invites the reader to assume the
 * material is in, which is the one wrong conclusion this read exists to stop.
 *
 * `counted_classes` is the coverage of the ledger's own aggregates, reported so
 * that any figure derived from this census can say what it covers. It is not
 * selectable: the backend takes no parameter for it, deliberately, so that a
 * screen cannot show a coverage the totals beside it were never computed
 * against.
 */

/**
 * One proof class in one case, exactly as `ClassStanding.as_dict` in
 * `backend/services/financial/proof_standing.py` emits it.
 *
 * `proof_class` is typed `string` rather than `ProofClass`, for the reason
 * `LedgerTransaction` gives: a backend one version ahead can send a member this
 * build has never heard of, and a union would let it through while claiming it
 * had been checked. Narrowing is a runtime job.
 *
 * The four booleans are the backend's answers, not restatements of a rule this
 * file knows. Nothing here may derive them from `proof_class` instead: a reader
 * that got `requires_adjudication` wrong would show unadjudicated material as
 * though it had been verified.
 */
export interface ClassStanding {
  /** One of `PROOF_CLASSES`, narrowed rather than trusted. */
  proof_class: string
  /** Source documents carrying this class, whatever their status. */
  documents: number
  /** Ledger rows carrying this class, whatever their status. */
  transactions: number
  /** Enters the verified ledger with no human act. */
  admits_automatically: boolean
  /** A recorded human verdict is the only route into the ledger. */
  requires_adjudication: boolean
  /** May yield ledger rows at all. False only for `p4`. */
  may_produce_ledger_rows: boolean
  /** Participates in an aggregate under `counted_classes` below. */
  counts_toward_totals: boolean
}

/**
 * A whole case's evidence, arranged by the class computed for it.
 *
 * Every class is present, including the ones holding nothing. A class with no
 * documents reports zero rather than being absent, because "this case has no
 * p3 documents" and "nothing here looked at p3" are different facts and a
 * missing key spells them the same way. Anything rendering this should show the
 * zeroes for the same reason.
 *
 * `documents` and `transactions` are the case's totals across every class, so
 * the breakdown can be checked against them. They are summed from the same
 * per-class figures on the backend, which is why they cannot disagree.
 */
export interface ProofStandingResponse {
  case_id: string
  /** Every class, in the backend enum's own order, present or not. */
  classes: ClassStanding[]
  documents: number
  transactions: number
  /**
   * The population sitting outside the verified ledger until someone rules on
   * it. Named for what it means rather than for the class, because the label is
   * the part a reader cannot interpret unaided.
   */
  documents_requiring_adjudication: number
  transactions_requiring_adjudication: number
  /** The classes the ledger's aggregates cover. Reported, not chosen. */
  counted_classes: string[]
}

/**
 * Every field a class standing carries, as a value rather than a type.
 *
 * The same device `DECISION_FIELDS` uses, and here it guards something
 * narrower: a permission dropped from this list is a permission that stops
 * reaching a screen while the counts beside it keep arriving, which looks like
 * nothing at all going wrong.
 */
export const CLASS_STANDING_FIELDS: readonly (keyof ClassStanding)[] = [
  "proof_class",
  "documents",
  "transactions",
  "admits_automatically",
  "requires_adjudication",
  "may_produce_ledger_rows",
  "counts_toward_totals",
]

/** Every field the census envelope carries. See `CLASS_STANDING_FIELDS`. */
export const PROOF_STANDING_FIELDS: readonly (keyof ProofStandingResponse)[] = [
  "case_id",
  "classes",
  "documents",
  "transactions",
  "documents_requiring_adjudication",
  "transactions_requiring_adjudication",
  "counted_classes",
]

/*
 * Overruling a hold on a file, and reading the refusal that asks for it.
 *
 * A file whose format the router cannot vouch for is held back from the
 * document pipeline rather than processed. Three routes enforce that -- two on
 * evidence, one on evidence folders -- and each refuses the whole request with
 * a 409 naming every held file it found. A named person may overrule the hold
 * on the record, and `POST /files/{id}/admit` is the only way to do it.
 *
 * The two shapes below are two halves of one exchange, which is why they are
 * declared together. The refusal carries everything the admission needs: the
 * file, what the router found in it, and who claims the format. That is
 * deliberate on the backend -- route-check is a separate request whose answer
 * may by then differ from the one the refusal was based on -- so an interface
 * that goes back to ask is not merely doing extra work, it is acting on a
 * second reading nobody refused anything over.
 *
 * `api.admission.test.ts` reads all three backend files and holds this build
 * to them.
 */

export const FILE_ADMISSION_OUTCOMES = [
  "admitted",
  "not_found",
  "nothing_to_override",
  "refused",
  "write_failed",
] as const
export type FileAdmissionOutcome = (typeof FILE_ADMISSION_OUTCOMES)[number]

/**
 * The router's finding, for the four findings that hold a file back.
 *
 * The route-check vocabulary is larger than this: `not_found` and `not_native`
 * are outcomes too, and neither holds anything back. Only these four ever
 * reach a refusal, so only these four ever need a reading.
 */
export const HELD_ROUTE_OUTCOMES = [
  "native",
  "ambiguous",
  "unreadable",
  "undetermined",
] as const
export type HeldRouteOutcome = (typeof HELD_ROUTE_OUTCOMES)[number]

/**
 * The shape of `FileAdmission.as_dict()`.
 *
 * `outcome` and `route_outcome` are typed `string` rather than as the unions
 * above, for the reason `RowAdjudication` gives: a backend one version ahead
 * can send a member this build has never heard of, and a union type would let
 * it through while claiming it had been checked.
 */
export interface FileAdmission {
  file_id: string
  /** One of `FILE_ADMISSION_OUTCOMES`, narrowed rather than trusted. */
  outcome: string
  /** True only for `admitted`. Derived on the backend. */
  admitted: boolean
  /**
   * `document_pipeline` when admitted, `held` otherwise. Derived from
   * `admitted` on the backend, so it cannot disagree with it.
   */
  routed_to: string
  /**
   * Overloaded by outcome, and must not be presented as one thing. On
   * `admitted` it is the grounds the person gave. On `nothing_to_override` and
   * `refused` it is why no decision was recorded.
   */
  reason: string | null
  file_name: string | null
  /**
   * What the router found at the moment the hold was overruled, re-read from
   * the file by the backend rather than taken from the request. A caller
   * cannot put a chosen finding into the permanent record.
   */
  route_outcome: string | null
  detected_format: string | null
  claimants: string[]
  /** Set only where a decision was actually appended to the log. */
  adjudication_id: string | null
}

/**
 * Every field an admission response carries, as a value rather than a type.
 *
 * The same device `ROW_ADJUDICATION_FIELDS` uses. Typed `keyof FileAdmission`,
 * so a name here the interface does not declare fails to compile; the contract
 * test closes the other direction against the Python.
 */
export const FILE_ADMISSION_FIELDS: readonly (keyof FileAdmission)[] = [
  "file_id",
  "outcome",
  "admitted",
  "routed_to",
  "reason",
  "file_name",
  "route_outcome",
  "detected_format",
  "claimants",
  "adjudication_id",
]

/**
 * One file named in a refusal: `HeldFile.as_dict()` on the backend.
 *
 * Every field here is needed to offer the admission. `claimants` is the list
 * of readers that claim the detected format, and it is the field that
 * distinguishes an `ambiguous` finding from the rest: more than one reader
 * claiming a file is why nothing could vouch for it.
 */
export interface HeldFile {
  file_id: string
  file_name: string | null
  /** One of `HELD_ROUTE_OUTCOMES`, narrowed rather than trusted. */
  route_outcome: string
  detected_format: string | null
  claimants: string[]
}

/** Every field a held file carries. See `FILE_ADMISSION_FIELDS`. */
export const HELD_FILE_FIELDS: readonly (keyof HeldFile)[] = [
  "file_id",
  "file_name",
  "route_outcome",
  "detected_format",
  "claimants",
]

/**
 * The body of a 409 from any route that sends files to the document pipeline.
 *
 * FastAPI wraps this under `detail`, and `ApiError.data` on this side holds the
 * whole parsed body, so the path to it is `data.detail`. Reading it is
 * `lib/admission-format.ts`'s job, not a caller's.
 *
 * `error` is the literal `unadmitted_files` and is how this refusal is told
 * apart from every other 409 the API can return. `held` names every offending
 * file rather than the first, so one refusal says everything that must be
 * decided; a reader that shows only the first turns a five-file batch into
 * five rounds of the same surprise.
 */
export interface UnadmittedFilesRefusal {
  error: string
  message: string
  held: HeldFile[]
}

/** Every field the refusal envelope carries. See `HELD_FILE_FIELDS`. */
export const UNADMITTED_FILES_REFUSAL_FIELDS: readonly (keyof UnadmittedFilesRefusal)[] =
  ["error", "message", "held"]

/**
 * The value of `error` on the refusal body, and the only thing that identifies
 * it. Exported so the reader and its tests name the same constant rather than
 * two copies of a string that only drift apart.
 */
export const UNADMITTED_FILES_ERROR = "unadmitted_files"

/**
 * What admitting one file needs.
 *
 * `reason` is not optional and has no default, matching the backend, which
 * requires it. It is the whole point of the route: the hold exists because
 * nothing could vouch for the file, and overruling it puts a named person's
 * judgement in its place. An admission with nothing on the record leaves
 * material in the pipeline that no reader passed and no one accounted for.
 *
 * There is deliberately no field for what the router found. The backend
 * re-reads that from the file, so a request cannot put a chosen finding into
 * the permanent record.
 */
export interface AdmitFileParams {
  caseId: string
  fileId: string
  reason: string
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

  /**
   * Hold one stored row out of the ledger's totals, on a person's authority.
   *
   * The grounds recorded are always `adjudicated` and cannot be set from here.
   * The other grounds this ledger knows are decided against a reconciled
   * period rather than against a request, and are unreachable over HTTP by
   * design: a class a person raised must not be able to pass for one the
   * arithmetic proved.
   *
   * The answer is worth reading even when it succeeded. `rescues_period` on a
   * `quarantined` outcome is the only place the ledger will ever say that this
   * removal is what made the period balance.
   */
  quarantineRow: (params: RowAdjudicationParams) =>
    fetchAPI<RowAdjudication>(
      `/api/financial/transactions/${encodeURIComponent(params.transactionId)}` +
        `/quarantine?${new URLSearchParams({ case_id: params.caseId })}`,
      { method: "POST", body: { reason: params.reason } }
    ),

  /**
   * Return one quarantined row to the ledger's totals.
   *
   * Not an undo. The backend appends the reversal after the quarantine rather
   * than deleting it, so the log ends up holding the setting aside, its
   * grounds, the reversal and the person who took each. Nothing here removes a
   * record.
   */
  releaseRow: (params: RowAdjudicationParams) =>
    fetchAPI<RowAdjudication>(
      `/api/financial/transactions/${encodeURIComponent(params.transactionId)}` +
        `/release?${new URLSearchParams({ case_id: params.caseId })}`,
      { method: "POST", body: { reason: params.reason } }
    ),

  /**
   * What has been decided in one case, newest first.
   *
   * A read, despite sitting beside the two writes above, and it is on the
   * ledger router rather than the adjudication one for that reason: the
   * adjudication router puts every route behind the write bar on purpose, and
   * reading a history needs no more permission than reading the rows does.
   *
   * **No limit or offset is sent unless one was asked for.** The endpoint has
   * its own default page size and its own cap, and both are enforced by the
   * service that knows the difference between them -- a limit below 1 is
   * refused, a limit above the cap is capped and answered. A default sent from
   * here would be a second copy of a bound that only drifts, and a bound
   * declared on this side would turn a request the backend is willing to serve
   * into a rejection it never saw.
   *
   * A limit of `0` is therefore sent rather than dropped, so the caller gets
   * the backend's refusal instead of silently receiving a full page.
   *
   * The answer carries `total` and `truncated` beside the records. Hand the
   * response on whole; a page rebuilt field by field is one careless edit away
   * from losing the two figures that say what is not being shown.
   */
  getCaseDecisions: (params: CaseDecisionsParams) => {
    const qs = new URLSearchParams({ case_id: params.caseId })
    if (params.subjectType) qs.set("subject_type", params.subjectType)
    if (params.subjectId) qs.set("subject_id", params.subjectId)
    if (params.decision) qs.set("decision", params.decision)
    if (params.limit !== undefined) qs.set("limit", String(params.limit))
    if (params.offset !== undefined) qs.set("offset", String(params.offset))
    return fetchAPI<DecisionsResponse>(`/api/financial/decisions?${qs}`)
  },

  /**
   * How this case's evidence stands by proof class, and what each class lets
   * the case do with it.
   *
   * **Takes the case and nothing else.** No status filter, no date range, no
   * choice of which classes count toward totals. It is a census, so the
   * per-class figures add up to the case's documents and rows, and that is the
   * property that makes the breakdown checkable at a glance. A filter would
   * quietly break it while the response looked identical.
   *
   * Hand the response on whole. The permissions travel with the counts on
   * purpose, and a shape rebuilt field by field is one careless edit away from
   * dropping them and leaving numbers against labels nobody can read.
   */
  getCaseProofStanding: (caseId: string) =>
    fetchAPI<ProofStandingResponse>(
      `/api/financial/proof-standing?${new URLSearchParams({ case_id: caseId })}`
    ),

  /**
   * Overrule the hold on one file, on a person's authority.
   *
   * **This records an authority. It processes nothing.** A 200 here means the
   * override is on the record, not that the file has moved; the caller must
   * still send the request that was refused. Treating the answer as though the
   * work were done would leave a file admitted and never processed, which
   * looks from every screen exactly like a file that was processed.
   *
   * Almost nothing this route can say is an error, and the two that are do not
   * come back as answers: a missing file is a 404 and a failed write is a 500.
   * Everything else is a 200 carrying its own outcome, including `refused` and
   * `nothing_to_override`. That last one is a fact rather than a fault -- the
   * router is not holding this file, so there is no no to overrule and nothing
   * stops it being processed. Reporting it as a failure would send someone
   * looking for a problem that does not exist.
   *
   * **Nothing is deduplicated, here or on the backend.** Calling this twice
   * writes two decisions. The backend currently checks for the existence of a
   * decision, not its consumption; retries of processing must not automatically
   * call this method again.
   */
  admitFile: (params: AdmitFileParams) =>
    fetchAPI<FileAdmission>(
      `/api/financial/files/${encodeURIComponent(params.fileId)}` +
        `/admit?${new URLSearchParams({ case_id: params.caseId })}`,
      { method: "POST", body: { reason: params.reason } }
    ),
}
