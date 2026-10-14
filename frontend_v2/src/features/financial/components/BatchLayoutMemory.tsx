import { useState } from "react"
import { useMutation, useQuery } from "@tanstack/react-query"
import { z } from "zod"
import { Button } from "@/components/ui/button"
import { fetchAPI } from "@/lib/api-client"
import { newReviewId } from "../lib/statement-review-id"

const confirmation = z.object({
  id: z.string(),
  value: z.string(),
  confirmed_at: z.string(),
  confirmed_by: z.object({ name: z.string().nullable().optional() }).passthrough(),
})
const group = z.object({
  key: z.string(),
  field: z.enum(["holder", "institution", "currency"]),
  label: z.string(),
  account: z.string(),
  printed: z.array(z.string()),
  proposal: z.string(),
  proposal_basis: z.string(),
  confirmations: z.array(confirmation),
  conflict: z.boolean(),
  statement_count: z.number(),
  money_proved_count: z.number(),
  statements: z.array(
    z.object({
      item_id: z.string(),
      file_id: z.string(),
      statement_id: z.string(),
      filename: z.string(),
      period_start: z.string(),
      period_end: z.string(),
      money_proved: z.boolean(),
    })
  ),
})
const listing = z.object({
  case_id: z.string(),
  batch_id: z.string(),
  groups: z.array(group),
})
type Group = z.infer<typeof group>

const BASIS: Record<string, string> = {
  confirmed_for_this_account:
    "Confirmed earlier for this account on another printing.",
  printed_addressee: "Printed at the top of the address block.",
  printed_legal_name: "Printed as the bank's legal name on these pages.",
  printed_currency_name: "Printed as the currency of these statements.",
}

/** One confirmation per printed layout, account and missing detail. */
export function BatchLayoutMemory({
  caseId,
  batchId,
  onSaved,
}: {
  caseId: string
  batchId: string
  onSaved: () => void
}) {
  const [open, setOpen] = useState(false)
  const [values, setValues] = useState<Record<string, string>>({})
  const [reasons, setReasons] = useState<Record<string, string>>({})
  const [message, setMessage] = useState("")
  const base = "/api/financial/statement-import"
  const query = useQuery({
    queryKey: ["batch-layout-memory", caseId, batchId],
    enabled: open,
    retry: false,
    refetchOnWindowFocus: false,
    queryFn: async () => {
      const result = listing.parse(
        await fetchAPI(
          `${base}/batches/${encodeURIComponent(batchId)}/layout-memory?case_id=${caseId}`
        )
      )
      if (result.case_id !== caseId || result.batch_id !== batchId)
        throw Error("The statements belong to another batch.")
      return result.groups
    },
  })
  const confirm = useMutation({
    retry: false,
    mutationFn: async ({ item, value }: { item: Group; value: string }) => {
      const first = item.statements[0]
      const result = z
        .object({
          case_id: z.string(),
          already_confirmed: z.boolean(),
          refreshed: z
            .object({ refreshed: z.number().optional() })
            .passthrough(),
        })
        .parse(
          await fetchAPI(`${base}/layout-memory/confirm?case_id=${caseId}`, {
            method: "POST",
            body: {
              file_id: first.file_id,
              statement_id: first.statement_id,
              field: item.field,
              value,
              key: item.key,
              request_id: newReviewId(),
            },
          })
        )
      if (result.case_id !== caseId)
        throw Error("The response belongs to another case.")
      return { item, value, result }
    },
    onSuccess: ({ item, value, result }) => {
      setMessage(
        `${value} confirmed as the ${item.label} for ${item.statement_count} statements of account ${item.account}. ` +
          `${result.refreshed.refreshed ?? 0} were checked again; statements with other problems stay in review.`
      )
      void query.refetch()
      onSaved()
    },
  })
  const withdraw = useMutation({
    retry: false,
    mutationFn: async ({ id, reason }: { id: string; reason: string }) =>
      fetchAPI(
        `${base}/layout-memory/${encodeURIComponent(id)}/withdraw?case_id=${caseId}`,
        { method: "POST", body: { reason } }
      ),
    onSuccess: () => {
      setMessage(
        "Confirmation withdrawn. The statements it completed are checked again and wait for a decision."
      )
      void query.refetch()
      onSaved()
    },
  })
  const groups = query.data || []
  return (
    <section
      className="rounded border p-3 space-y-3"
      aria-label="Confirm account details once per layout"
    >
      <Button variant="outline" onClick={() => setOpen(!open)}>
        Confirm details once for matching statements
      </Button>
      {message && <p role="status">{message}</p>}
      {(confirm.isError || withdraw.isError) && (
        <p role="alert">
          {(confirm.error || withdraw.error)?.message} Nothing else was
          changed. Refresh the list and retry.
        </p>
      )}
      {open && query.isLoading && <p>Loading statements…</p>}
      {open && query.isError && <p role="alert">{query.error.message}</p>}
      {open && query.isSuccess && groups.length === 0 && (
        <p>No statements in this batch wait for a detail that can be confirmed once.</p>
      )}
      {open &&
        groups.map((item) => {
          const value = values[item.key] ?? item.proposal
          const active = item.confirmations[0]
          return (
            <article
              key={item.key + item.field}
              className="rounded border p-3 space-y-2"
              aria-label={`${item.label} for account ${item.account}`}
            >
              <h4 className="font-semibold">
                {item.label[0].toUpperCase() + item.label.slice(1)} · account{" "}
                {item.account} · {item.statement_count} statements
              </h4>
              <p className="text-sm">
                {item.money_proved_count} of {item.statement_count} have balances
                that reconcile with every payment. A confirmed {item.label}{" "}
                completes only those; the others stay in review for their own
                reasons.
              </p>
              {item.printed.length > 0 && (
                <p className="text-sm">
                  Printed on these statements: {item.printed.join(" · ")}
                </p>
              )}
              {item.proposal_basis && (
                <p className="text-sm">{BASIS[item.proposal_basis]}</p>
              )}
              {active ? (
                <div className="space-y-1">
                  <p className="text-sm">
                    Confirmed: {active.value}
                    {active.confirmed_by.name
                      ? ` by ${active.confirmed_by.name}`
                      : ""}
                  </p>
                  <label className="text-sm block">
                    Reason to withdraw
                    <input
                      className="ml-2 rounded border px-2 py-1"
                      maxLength={500}
                      value={reasons[active.id] || ""}
                      onChange={(e) =>
                        setReasons({ ...reasons, [active.id]: e.target.value })
                      }
                    />
                  </label>
                  <Button
                    variant="outline"
                    disabled={!reasons[active.id]?.trim() || withdraw.isPending}
                    onClick={() =>
                      withdraw.mutate({
                        id: active.id,
                        reason: reasons[active.id].trim(),
                      })
                    }
                  >
                    Withdraw this confirmation
                  </Button>
                </div>
              ) : (
                <div className="flex flex-wrap items-center gap-2">
                  <label className="text-sm">
                    {item.label[0].toUpperCase() + item.label.slice(1)} shown on
                    the statements
                    <input
                      className="ml-2 rounded border px-2 py-1"
                      maxLength={128}
                      value={value}
                      onChange={(e) =>
                        setValues({ ...values, [item.key]: e.target.value })
                      }
                    />
                  </label>
                  <Button
                    disabled={!value.trim() || confirm.isPending}
                    onClick={() =>
                      confirm.mutate({ item, value: value.trim() })
                    }
                  >
                    Confirm for {item.statement_count} statements
                  </Button>
                </div>
              )}
              <details>
                <summary className="text-sm">Statements in this group</summary>
                <ul className="text-sm">
                  {item.statements.map((s) => (
                    <li key={s.item_id}>
                      {s.filename} · {s.period_start} to {s.period_end}
                      {s.money_proved ? "" : " · balances not yet reconciled"}
                    </li>
                  ))}
                </ul>
              </details>
            </article>
          )
        })}
    </section>
  )
}
