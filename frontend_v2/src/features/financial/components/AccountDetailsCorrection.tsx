import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { z } from "zod"
import { Button } from "@/components/ui/button"
import { fetchAPI } from "@/lib/api-client"
import { useFinancialAccess } from "../hooks/use-financial-access"

const statement = z.object({
  source_document_id: z.string(),
  period_start: z.string().nullable(),
  period_end: z.string().nullable(),
  currency: z.string().nullable(),
  holder: z.string(),
  institution: z.string(),
})
const values = z.object({ holder: z.string(), institution: z.string() })
const historyEntry = z.object({
  id: z.string(),
  kind: z.string(),
  at: z.string(),
  reason: z.string(),
  actor_name: z.string(),
  before: values,
  after: values,
  undone_at: z.string().optional(),
})
const state = z.object({
  case_id: z.string(),
  account_id: z.string(),
  holder: z.string(),
  institution: z.string(),
  account_number: z.string(),
  currency: z.string(),
  statements: z.array(statement),
  history: z.array(historyEntry),
  revision: z.string(),
})
const preview = z.object({
  case_id: z.string(),
  account_id: z.string(),
  before: values,
  after: values,
  statements: z.array(statement),
  rejoin: z.array(
    z.object({ account_id: z.string(), statements: z.array(statement) })
  ),
  revision: z.string(),
})
type Statement = z.infer<typeof statement>

const period = (s: Statement) =>
  `${s.period_start || "start not read"} to ${s.period_end || "end not read"}`
const count = (n: number, one: string, many: string) =>
  `${n} ${n === 1 ? one : many}`

/**
 * Correct an account's holder or bank for every statement it holds. A
 * statement's own details edit only changes that statement; when the account
 * itself is wrong, this corrects it once, records the change on each
 * statement, and brings back statements an earlier edit moved onto an
 * account of their own. The earlier values stay in the history and the
 * correction can be undone.
 */
export function AccountDetailsCorrection({
  caseId,
  accountId,
}: {
  caseId: string
  accountId: string
}) {
  const { canEdit } = useFinancialAccess()
  const client = useQueryClient()
  const [holder, setHolder] = useState("")
  const [institution, setInstitution] = useState("")
  const [reason, setReason] = useState("")
  const [proposal, setProposal] = useState<z.infer<typeof preview> | null>(null)
  const [notice, setNotice] = useState("")
  const base = `/api/financial/statement-import/accounts/${encodeURIComponent(accountId)}/details`
  const key = ["account-details", caseId, accountId]
  const query = useQuery({
    queryKey: key,
    retry: false,
    queryFn: async () => {
      const result = state.parse(
        await fetchAPI(`${base}?case_id=${encodeURIComponent(caseId)}`)
      )
      if (result.case_id !== caseId || result.account_id !== accountId)
        throw Error("This account belongs to another case.")
      return result
    },
  })
  const body = () => ({
    expected_revision: query.data!.revision,
    holder: holder.trim() || null,
    institution: institution.trim() || null,
    reason,
  })
  const review = useMutation({
    retry: false,
    mutationFn: async () =>
      preview.parse(
        await fetchAPI(
          `${base}/preview?case_id=${encodeURIComponent(caseId)}`,
          { method: "POST", body: body() }
        )
      ),
    onSuccess: (result) => {
      if (result.case_id !== caseId)
        throw Error("The preview belongs to another case.")
      setNotice("")
      setProposal(result)
    },
  })
  const save = useMutation({
    retry: false,
    mutationFn: async () =>
      state.parse(
        await fetchAPI(`${base}?case_id=${encodeURIComponent(caseId)}`, {
          method: "POST",
          body: { ...body(), expected_revision: proposal!.revision },
        })
      ),
    onSuccess: (result) => {
      client.setQueryData(key, result)
      setProposal(null)
      setHolder("")
      setInstitution("")
      setReason("")
      setNotice(
        `Account corrected for ${count(result.statements.length, "statement", "statements")}. The earlier values remain in the account history.`
      )
      void client.invalidateQueries()
    },
  })
  const undo = useMutation({
    retry: false,
    mutationFn: async (correctionId: string) =>
      state.parse(
        await fetchAPI(`${base}/undo?case_id=${encodeURIComponent(caseId)}`, {
          method: "POST",
          body: {
            expected_revision: query.data!.revision,
            correction_id: correctionId,
            reason,
          },
        })
      ),
    onSuccess: (result) => {
      client.setQueryData(key, result)
      setNotice("Correction undone. The earlier holder and bank are back.")
      void client.invalidateQueries()
    },
  })
  if (query.isPending) return <p role="status">Loading account…</p>
  if (query.isError)
    return (
      <p className="text-sm text-muted-foreground">
        The account could not be loaded. Reopen this statement to try again.
      </p>
    )
  const data = query.data
  const failure = review.error || save.error || undo.error
  const latest = [...data.history]
    .reverse()
    .find((item) => item.kind === "correction" && !item.undone_at)
  const ready =
    reason.trim() !== "" &&
    ((holder.trim() !== "" && holder.trim() !== data.holder) ||
      (institution.trim() !== "" && institution.trim() !== data.institution))
  return (
    <section
      aria-label="Account holder and bank"
      className="space-y-2 rounded border p-3 text-sm"
    >
      <h3 className="font-semibold">Account holder and bank</h3>
      <p>
        <span className="font-medium">
          {data.holder || "Holder not recorded"}
        </span>
        {data.institution ? ` · ${data.institution}` : ""}
        {data.account_number ? ` · ${data.account_number}` : ""} ·{" "}
        {count(data.statements.length, "statement", "statements")}
      </p>
      <p className="text-muted-foreground">
        Use this when the account itself is wrong, for example a holder read
        from the address. It corrects every statement of this account at once.
        To change only this statement, use its details above.
      </p>
      {canEdit && (
        <div className="grid gap-2 sm:grid-cols-2">
          <label className="flex flex-col gap-1">
            Holder as printed
            <input
              className="rounded border bg-background p-1"
              value={holder}
              placeholder={data.holder}
              onChange={(event) => {
                setHolder(event.target.value)
                setProposal(null)
              }}
            />
          </label>
          <label className="flex flex-col gap-1">
            Bank as printed
            <input
              className="rounded border bg-background p-1"
              value={institution}
              placeholder={data.institution}
              onChange={(event) => {
                setInstitution(event.target.value)
                setProposal(null)
              }}
            />
          </label>
          <label className="flex flex-col gap-1 sm:col-span-2">
            Reason (where it is printed)
            <input
              className="rounded border bg-background p-1"
              value={reason}
              onChange={(event) => {
                setReason(event.target.value)
                setProposal(null)
              }}
            />
          </label>
          <div className="sm:col-span-2">
            <Button
              type="button"
              size="sm"
              variant="outline"
              disabled={!ready || review.isPending}
              onClick={() => review.mutate()}
            >
              Review account correction
            </Button>
          </div>
        </div>
      )}
      {proposal && (
        <div className="space-y-1 rounded bg-muted/40 p-2">
          <p>
            {proposal.before.holder || "No holder"} →{" "}
            {proposal.after.holder || "No holder"}
            {proposal.before.institution !== proposal.after.institution
              ? ` · ${proposal.before.institution || "No bank"} → ${proposal.after.institution}`
              : ""}
          </p>
          <p>
            {count(proposal.statements.length, "statement", "statements")} of
            this account will show the corrected details.
          </p>
          {proposal.rejoin.length > 0 && (
            <ul className="space-y-1">
              {proposal.rejoin.flatMap((item) =>
                item.statements.map((s) => (
                  <li key={s.source_document_id}>
                    Statement {period(s)} was moved onto its own account by an
                    earlier edit and comes back to this account.
                  </li>
                ))
              )}
            </ul>
          )}
          <Button
            type="button"
            size="sm"
            disabled={save.isPending}
            onClick={() => save.mutate()}
          >
            {save.isPending ? "Saving…" : "Correct the account"}
          </Button>
        </div>
      )}
      {latest && (
        <div className="space-y-1">
          <p>
            Last corrected by {latest.actor_name}: {latest.before.holder} →{" "}
            {latest.after.holder}. Reason: {latest.reason}
          </p>
          {canEdit && (
            <Button
              type="button"
              size="sm"
              variant="outline"
              disabled={undo.isPending || !reason.trim()}
              title={reason.trim() ? undefined : "Enter the reason first"}
              onClick={() => undo.mutate(latest.id)}
            >
              Undo this correction (give the reason above)
            </Button>
          )}
        </div>
      )}
      {notice && <p role="status">{notice}</p>}
      {failure && (
        <p role="alert">
          {failure instanceof Error ? failure.message : "The change failed."}{" "}
          Nothing was changed.
        </p>
      )}
    </section>
  )
}
