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
}
