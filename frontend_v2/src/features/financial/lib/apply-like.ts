import { toast } from "sonner"
import type { QueryClient } from "@tanstack/react-query"
import { fetchAPI } from "@/lib/api-client"

/**
 * After a person sets one payment's category: if other payments in the case
 * read the same (or name the same counterparty) and no person has chosen
 * their category, offer to give them this one in a single click.
 */
export async function offerApplyLike(
  client: QueryClient,
  caseId: string,
  transactionId: string,
  category: string
) {
  const params = new URLSearchParams({ case_id: caseId })
  let like: { case_id: string; count: number; transaction_ids: string[] }
  try {
    like = await fetchAPI(
      `/api/financial/ledger/payment-categories/like?${new URLSearchParams({ case_id: caseId, transaction_id: transactionId })}`
    )
  } catch {
    return
  }
  if (like.case_id !== caseId || !like.count) return
  const name = category || "Uncategorized"
  toast(`${like.count} similar ${like.count === 1 ? "payment" : "payments"}`, {
    description: `Give ${like.count === 1 ? "it" : "them"} the category ${name} too?`,
    duration: 15000,
    action: {
      label: `Apply to ${like.count}`,
      onClick: async () => {
        try {
          const result = await fetchAPI<{ case_id: string; updated: number }>(
            `/api/financial/ledger/payment-categories/apply-like?${params}`,
            {
              method: "POST",
              body: {
                transaction_id: transactionId,
                category: name,
                transaction_ids: like.transaction_ids,
              },
            }
          )
          await client.invalidateQueries({
            predicate: (query) =>
              /financial|ledger|payment/.test(String(query.queryKey[0])) &&
              query.queryKey.includes(caseId),
          })
          toast.success(
            `${name} applied to ${result.updated} similar ${result.updated === 1 ? "payment" : "payments"}.`
          )
        } catch {
          toast.error(
            "The category could not be applied to the similar payments."
          )
        }
      },
    },
  })
}
