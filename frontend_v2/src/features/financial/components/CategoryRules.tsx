import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { fetchAPI } from "@/lib/api-client"
import { useFinancialAccess } from "../hooks/use-financial-access"

type CategoryRule = {
  id: string
  match_kind: "description" | "counterparty"
  match_value: string
  example: string
  category: string
  active: boolean
  created_by: string | null
  created_at: string | null
  placed: number
  person_chose_differently: number
}

/** Category rules people made ("Make this a rule for future statements"), with each rule's track record. */
export function CategoryRulesTable({ caseId }: { caseId: string }) {
  const { canEdit } = useFinancialAccess()
  const client = useQueryClient()
  const query = useQuery({
    queryKey: ["financial-category-rules", caseId],
    queryFn: async () => {
      const data = await fetchAPI<{ case_id: string; rules: CategoryRule[] }>(
        `/api/financial/ledger/payment-categories/rules?${new URLSearchParams({ case_id: caseId })}`
      )
      if (data.case_id !== caseId) throw Error("The rules came from a different case.")
      return data.rules
    },
    retry: false,
    refetchOnWindowFocus: false,
  })
  const retire = useMutation({
    mutationFn: (id: string) =>
      fetchAPI(
        `/api/financial/ledger/payment-categories/rules/${encodeURIComponent(id)}/retire?${new URLSearchParams({ case_id: caseId })}`,
        { method: "POST", body: {} }
      ),
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: ["financial-category-rules", caseId] })
      toast.success("The rule no longer places new payments. Payments it placed keep their category.")
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : "The rule could not be stopped."),
  })
  if (query.isError) return <p role="alert">Category rules could not be loaded: {query.error.message}</p>
  if (!query.data?.length)
    return query.isPending ? null : (
      <p className="text-muted-foreground">
        No category rules yet. Tick “Make this a rule for future statements too” when categorising a payment.
      </p>
    )
  return (
    <table className="w-full text-left" aria-label="Category rule track record">
      <thead>
        <tr>
          <th>Category rule</th>
          <th className="text-right">Payments placed</th>
          <th className="text-right">A person chose otherwise</th>
          <th />
        </tr>
      </thead>
      <tbody>
        {query.data.map((rule) => (
          <tr key={rule.id} className={rule.active ? "" : "text-muted-foreground"}>
            <td>
              {rule.match_kind === "description" ? "Described like" : "Counterparty"} “
              {rule.example.slice(0, 60) || rule.match_value}” → <strong>{rule.category || "Uncategorized"}</strong>
              {rule.created_by ? <span className="block text-xs text-muted-foreground">by {rule.created_by}</span> : null}
              {!rule.active && <span className="block text-xs">Stopped</span>}
            </td>
            <td className="text-right tabular-nums">{rule.placed}</td>
            <td className="text-right tabular-nums">{rule.person_chose_differently}</td>
            <td className="text-right">
              {canEdit && rule.active && (
                <Button size="sm" variant="outline" disabled={retire.isPending} onClick={() => retire.mutate(rule.id)}>
                  Stop using
                </Button>
              )}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}
