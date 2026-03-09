import { fetchAPI } from "@/lib/api-client"

export interface Transaction {
  key: string
  date: string
  amount: number
  currency?: string
  category?: string
  description?: string
  from_key?: string
  from_name?: string
  to_key?: string
  to_name?: string
  purpose?: string
  counterparty_details?: string
  notes?: string
  parent_key?: string
  case_id: string
}

export interface FinancialSummary {
  total_inflow: number
  total_outflow: number
  net_flow: number
  transaction_count: number
  category_breakdown: Record<string, number>
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

export const financialAPI = {
  getTransactions: (params: {
    caseId: string
    types?: string[]
    startDate?: string
    endDate?: string
    categories?: string[]
  }) => {
    const qs = new URLSearchParams({ case_id: params.caseId })
    if (params.types?.length) qs.set("types", params.types.join(","))
    if (params.startDate) qs.set("start_date", params.startDate)
    if (params.endDate) qs.set("end_date", params.endDate)
    if (params.categories?.length) qs.set("categories", params.categories.join(","))
    return fetchAPI<Transaction[]>(`/api/financial?${qs}`)
  },

  getSummary: (caseId: string) =>
    fetchAPI<FinancialSummary>(`/api/financial/summary?case_id=${caseId}`),

  getVolume: (caseId: string) =>
    fetchAPI<unknown>(`/api/financial/volume?case_id=${caseId}`),

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

  getCategories: (caseId: string) =>
    fetchAPI<FinancialCategory[]>(`/api/financial/categories?case_id=${caseId}`),

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

  getSubTransactions: (parentKey: string, caseId: string) =>
    fetchAPI<Transaction[]>(
      `/api/financial/transactions/${encodeURIComponent(parentKey)}/sub-transactions?case_id=${caseId}`
    ),
}
