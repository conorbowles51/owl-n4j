import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { z } from "zod"
import { Button } from "@/components/ui/button"
import { fetchAPI } from "@/lib/api-client"
import { randomRequestId } from "@/lib/browser-crypto"
import { useFinancialAccess } from "../hooks/use-financial-access"
import { AccountTypeEditor } from "./AccountTypeEditor"

const review = z.object({
  case_id: z.string(),
  accounts: z.array(
    z.object({
      account_id: z.string(),
      label: z.string(),
      institution: z.string(),
      account_type: z.string(),
      statement_count: z.number(),
      card_signals: z.array(z.string()),
      suggested_type: z.string().nullable(),
      flagged_rows: z.number(),
    })
  ),
  same_card: z.array(
    z.object({ account_ids: z.array(z.string()), reason: z.string() })
  ),
})
const consolidation = z.object({ case_id: z.string(), revision: z.string() })
const MERGE_REASON =
  "Same printed card number from the same bank, recorded as two accounts."

/**
 * Account types to check in Review accounts: accounts whose statements print
 * card wording but are not recorded as cards, rows flagged after a type
 * change, and accounts that are the same printed card (offered for the
 * existing reversible merge, which keeps every statement and payment).
 */
export function AccountTypeReview({
  caseId,
  active = true,
}: {
  caseId: string
  active?: boolean
}) {
  const { canEdit } = useFinancialAccess()
  const client = useQueryClient()
  const [merged, setMerged] = useState("")
  const query = useQuery({
    queryKey: ["account-type-review", caseId],
    enabled: active,
    retry: false,
    queryFn: async () => {
      const result = review.parse(
        await fetchAPI(
          `/api/financial/statement-import/account-types?case_id=${encodeURIComponent(caseId)}`
        )
      )
      if (result.case_id !== caseId)
        throw Error("The accounts belong to another case.")
      return result
    },
  })
  const merge = useMutation({
    retry: false,
    mutationFn: async (accountIds: string[]) => {
      const current = consolidation.parse(
        await fetchAPI(
          `/api/financial/account-consolidations?case_id=${encodeURIComponent(caseId)}`
        )
      )
      const body = {
        request_id: randomRequestId(),
        expected_revision: current.revision,
        account_ids: accountIds,
        retained_id: accountIds[0],
        reason: MERGE_REASON,
      }
      const checked = consolidation.parse(
        await fetchAPI(
          `/api/financial/account-consolidations/preview?case_id=${encodeURIComponent(caseId)}`,
          { method: "POST", body }
        )
      )
      return fetchAPI(
        `/api/financial/account-consolidations?case_id=${encodeURIComponent(caseId)}`,
        { method: "POST", body: { ...body, expected_revision: checked.revision } }
      )
    },
    onSuccess: () => {
      setMerged(
        "Accounts merged. Their statements and payments are unchanged and the merge can be undone under Merge duplicate accounts, in Merge history and undo."
      )
      void client.invalidateQueries()
    },
  })
  if (!query.data) return null
  const label = (id: string) =>
    query.data.accounts.find((account) => account.account_id === id)?.label ??
    id.slice(0, 8)
  const attention = query.data.accounts.filter(
    (account) => account.suggested_type || account.flagged_rows
  )
  if (!attention.length && !query.data.same_card.length && !merged) return null
  return (
    <section
      aria-label="Account types to check"
      className="space-y-3 rounded border p-3 my-3"
    >
      <h3 className="font-semibold">Account types to check</h3>
      {query.data.same_card.map((group) => (
        <div
          key={group.account_ids.join(":")}
          className="space-y-1 rounded border p-2 text-sm"
        >
          <p>
            One card recorded as {group.account_ids.length} accounts:{" "}
            {group.account_ids.map(label).join(" and ")}. {group.reason}
          </p>
          {canEdit && (
            <Button
              type="button"
              size="sm"
              disabled={merge.isPending}
              onClick={() => merge.mutate(group.account_ids)}
            >
              {merge.isPending ? "Merging…" : "Merge into one account"}
            </Button>
          )}
        </div>
      ))}
      {merged && <p role="status">{merged}</p>}
      {merge.isError && (
        <p role="alert">
          {merge.error instanceof Error
            ? merge.error.message
            : "The accounts could not be merged."}{" "}
          Nothing was changed.
        </p>
      )}
      {!!attention.length && (
        <AccountTypeEditor
          caseId={caseId}
          accountIds={attention.map((account) => account.account_id)}
        />
      )}
    </section>
  )
}
