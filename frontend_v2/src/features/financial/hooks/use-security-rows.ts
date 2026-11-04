import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { fetchAPI } from "@/lib/api-client"

export type SecurityRowKind = "trade" | "holding"

export type SecurityCorrection = {
  read: string | number | null
  value: string | number | null
  reason: string
  by?: { name?: string | null }
  at?: string
}

export type SecurityRow = {
  id: string
  row_kind: SecurityRowKind
  side: string | null
  holding_kind: string | null
  operation: string | null
  instrument: string
  isin: string | null
  quantity: string | null
  quantity_printed: string | null
  price: string | null
  currency: string | null
  gross_minor: number | null
  commission_minor: number | null
  premium_minor: number | null
  tax_minor: number | null
  net_minor: number | null
  market_value_minor: number | null
  trade_date: string | null
  settlement_date: string | null
  as_of_date: string | null
  execution_time: string | null
  term_days: number | null
  rate_printed: string | null
  proof_class: string
  account: string | null
  file: string | null
  evidence_file_id: string
  cash_transaction_id: string | null
  citation: {
    file_id: string
    page: number | null
    printed_text: string | null
    cash_leg?: { transaction_id: string; amount_minor: number; direction: string } | null
  }
  not_printed: string[]
  not_read: string[]
  /** Why a printed line could not be read with proof; its figures are then absent, never guessed. */
  unread?: string | null
  checks: Record<string, boolean | string>
  corrections: Record<string, SecurityCorrection>
  origin: { kind: "reader" | "model" | "confirmed"; text: string }
}

export type SecurityRowPage = {
  row_kind: SecurityRowKind
  total: number
  returned: number
  page: number
  page_size: number
  next_page: number | null
  items: SecurityRow[]
  not_shown_cash_leg_not_in_ledger: number
  revision: string | null
}

export const SECURITY_PAGE_SIZE = 50

export function useSecurityRows(
  caseId: string | undefined,
  kind: SecurityRowKind,
  instrument: string,
  page: number
) {
  return useQuery({
    queryKey: ["financial-ledger", caseId, "security-rows", kind, instrument, page],
    enabled: !!caseId,
    retry: false,
    queryFn: async () => {
      const params = new URLSearchParams({
        case_id: caseId!,
        kind,
        page: String(page),
        page_size: String(SECURITY_PAGE_SIZE),
      })
      if (instrument.trim()) params.set("instrument", instrument.trim())
      return (await fetchAPI(`/api/financial/security-rows?${params}`)) as SecurityRowPage
    },
  })
}

export function useSecurityRowAction(caseId: string | undefined) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: async ({
      id,
      action,
      body,
    }: {
      id: string
      action: "correct" | "confirm"
      body: Record<string, string>
    }) =>
      (await fetchAPI(
        `/api/financial/security-rows/${encodeURIComponent(id)}/${action}?${new URLSearchParams({ case_id: caseId! })}`,
        { method: "POST", body }
      )) as SecurityRow,
    onSuccess: () =>
      client.invalidateQueries({ queryKey: ["financial-ledger", caseId, "security-rows"] }),
  })
}
