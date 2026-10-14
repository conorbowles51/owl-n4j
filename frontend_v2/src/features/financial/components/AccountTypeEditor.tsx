import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { z } from "zod"
import { Button } from "@/components/ui/button"
import { fetchAPI } from "@/lib/api-client"
import { correctionMoney } from "../lib/correction-contract"
import { useFinancialAccess } from "../hooks/use-financial-access"

const TYPES = [
  ["credit_card", "Credit card"],
  ["checking", "Bank account (checking)"],
  ["savings", "Bank account (savings)"],
] as const
type AccountType = (typeof TYPES)[number][0]
const typeLabel = (value: string) =>
  TYPES.find(([key]) => key === value)?.[1] ??
  (value === "bank"
    ? "Bank account"
    : value === "other"
      ? "Other account"
      : "Not set")

const flaggedRow = z.object({
  transaction_id: z.string(),
  date: z.string().nullable(),
  description: z.string(),
  amount_minor: z.string(),
  direction: z.string(),
  proposed_direction: z.string(),
})
const statement = z.object({
  source_document_id: z.string(),
  period_start: z.string().nullable(),
  period_end: z.string().nullable(),
  currency: z.string().nullable(),
  convention_before: z.string(),
  convention_after: z.string(),
  reconciles: z.boolean().nullable(),
  reconciles_with_flagged_flipped: z.boolean().nullable(),
  // Flipped with the type change: adds up exactly only with them reversed.
  auto_flip: z.boolean().optional().default(false),
  flagged_rows: z.array(flaggedRow),
})
const state = z.object({
  case_id: z.string(),
  account_id: z.string(),
  account_type: z.string(),
  label: z.string(),
  institution: z.string(),
  statements: z.array(statement),
  card_signals: z.array(z.string()),
  suggested_type: z.string().nullable(),
  flagged_rows: z.number(),
  auto_flipped_rows: z.number().optional(),
  revision: z.string(),
})
const preview = z.object({
  case_id: z.string(),
  account_id: z.string(),
  account_type_after: z.string(),
  statements: z.array(statement),
  changed_statements: z.number(),
  flagged_rows: z.number(),
  auto_flip_rows: z.number().optional(),
  revision: z.string(),
})
type Statement = z.infer<typeof statement>

const period = (s: Statement) =>
  `${s.period_start || "start not read"} to ${s.period_end || "end not read"}`
const direction = (value: string) =>
  value === "credit" ? "money in" : "money out"

/**
 * Set or correct whether an account is a credit card or a bank account.
 * The change re-reads nothing: saved statements switch how their printed
 * balances read and are checked again. Rows the investigator entered under
 * the previous type are listed and flipped only when confirmed.
 */
export function AccountTypeEditor({
  caseId,
  accountIds,
}: {
  caseId: string
  accountIds: string[]
}) {
  const ids = [...new Set(accountIds)]
  if (!ids.length) return null
  return (
    <section aria-label="Account type" className="space-y-3 rounded border p-3">
      <h3 className="font-semibold">Account type</h3>
      <p className="text-sm text-muted-foreground">
        A credit card statement prints the amount owed; a bank statement prints
        the money held. Changing the type checks the saved statements again
        without reading the PDFs again. Your corrections stay, and the earlier
        type remains in the account history.
      </p>
      {ids.map((id) => (
        <AccountTypeRow key={id} caseId={caseId} accountId={id} />
      ))}
    </section>
  )
}

function AccountTypeRow({
  caseId,
  accountId,
}: {
  caseId: string
  accountId: string
}) {
  const { canEdit } = useFinancialAccess()
  const client = useQueryClient()
  const [choice, setChoice] = useState<AccountType | "">("")
  const [proposal, setProposal] = useState<z.infer<typeof preview> | null>(null)
  const [notice, setNotice] = useState("")
  const base = `/api/financial/statement-import/accounts/${encodeURIComponent(accountId)}/type`
  const query = useQuery({
    queryKey: ["account-type", caseId, accountId],
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
  const review = useMutation({
    retry: false,
    mutationFn: async (accountType: AccountType) =>
      preview.parse(
        await fetchAPI(
          `${base}/preview?case_id=${encodeURIComponent(caseId)}`,
          { method: "POST", body: { account_type: accountType } }
        )
      ),
    onSuccess: (result) => {
      if (result.case_id !== caseId)
        throw Error("The preview belongs to another case.")
      setProposal(result)
    },
  })
  const save = useMutation({
    retry: false,
    mutationFn: async () =>
      state.parse(
        await fetchAPI(`${base}?case_id=${encodeURIComponent(caseId)}`, {
          method: "POST",
          body: {
            account_type: proposal!.account_type_after,
            expected_revision: proposal!.revision,
            reason: "Account type set by the investigator.",
          },
        })
      ),
    onSuccess: (result) => {
      client.setQueryData(["account-type", caseId, accountId], result)
      setProposal(null)
      setChoice("")
      setNotice(
        `Saved as ${typeLabel(result.account_type).toLowerCase()}. ${result.statements.length} saved ${result.statements.length === 1 ? "statement was" : "statements were"} checked again.${result.auto_flipped_rows ? ` ${result.auto_flipped_rows} ${result.auto_flipped_rows === 1 ? "row you entered was" : "rows you entered were"} flipped because ${result.auto_flipped_rows === 1 ? "its statement" : "their statements"} now add up exactly; the originals stay in the correction history.` : ""}${result.flagged_rows ? ` ${result.flagged_rows} ${result.flagged_rows === 1 ? "row you entered is" : "rows you entered are"} listed below to check.` : ""}`
      )
      void client.invalidateQueries()
    },
  })
  const flip = useMutation({
    retry: false,
    mutationFn: async (target: Statement) =>
      state.parse(
        await fetchAPI(
          `${base}/flip-rows?case_id=${encodeURIComponent(caseId)}`,
          {
            method: "POST",
            body: {
              source_document_id: target.source_document_id,
              transaction_ids: target.flagged_rows.map(
                (row) => row.transaction_id
              ),
              expected_revision: query.data!.revision,
            },
          }
        )
      ),
    onSuccess: (result) => {
      client.setQueryData(["account-type", caseId, accountId], result)
      setNotice(
        "Rows flipped. The rows you entered remain in their correction history."
      )
      void client.invalidateQueries()
    },
  })
  if (query.isPending) return <p role="status">Loading account type…</p>
  if (query.isError)
    // Not an alert: the surrounding editor keeps working without it.
    return (
      <p className="text-sm text-muted-foreground">
        The account type could not be loaded. Reopen this statement to try
        again.
      </p>
    )
  const data = query.data
  const flagged = data.statements.filter((s) => s.flagged_rows.length)
  const failure = review.error || save.error || flip.error
  return (
    <div className="space-y-2 rounded border p-2 text-sm">
      <p>
        <span className="font-medium">{data.label}</span>
        {data.institution ? ` · ${data.institution}` : ""} ·{" "}
        {typeLabel(data.account_type)}
      </p>
      {data.suggested_type === "credit_card" && (
        <div className="space-y-1">
          <p>
            This looks like a credit card: its statements print{" "}
            {data.card_signals.join(", ")}.
          </p>
          {canEdit && (
            <Button
              type="button"
              size="sm"
              disabled={review.isPending || save.isPending}
              onClick={() => {
                setChoice("credit_card")
                review.mutate("credit_card")
              }}
            >
              Review change to credit card
            </Button>
          )}
        </div>
      )}
      {canEdit && (
        <label className="flex flex-wrap items-center gap-2">
          Change type to{" "}
          <select
            aria-label={`Account type for ${data.label}`}
            className="rounded border bg-background p-1"
            value={choice}
            onChange={(event) => {
              const value = event.target.value as AccountType | ""
              setChoice(value)
              setProposal(null)
              setNotice("")
              if (value) review.mutate(value)
            }}
          >
            <option value="">Choose…</option>
            {TYPES.filter(([key]) => key !== data.account_type).map(
              ([key, label]) => (
                <option key={key} value={key}>
                  {label}
                </option>
              )
            )}
          </select>
        </label>
      )}
      {proposal && (
        <div className="space-y-1 rounded bg-muted/40 p-2">
          <p>
            {proposal.changed_statements}{" "}
            {proposal.changed_statements === 1 ? "statement" : "statements"}{" "}
            will read{" "}
            {proposal.account_type_after === "credit_card"
              ? "printed balances as the amount owed"
              : "printed balances as money held"}
            . Nothing is read from the PDFs again.
          </p>
          <ul className="space-y-1">
            {proposal.statements.map((s) => (
              <li key={s.source_document_id}>
                Statement {period(s)}:{" "}
                {s.reconciles === null
                  ? "balances not recorded"
                  : s.reconciles
                    ? "adds up after the change"
                    : "does not add up after the change"}
                {s.flagged_rows.length
                  ? s.auto_flip
                    ? ` · ${s.flagged_rows.length} ${s.flagged_rows.length === 1 ? "row you entered" : "rows you entered"} will be flipped, because the statement adds up exactly with ${s.flagged_rows.length === 1 ? "it" : "them"} flipped and not without`
                    : ` · ${s.flagged_rows.length} ${s.flagged_rows.length === 1 ? "row you entered is" : "rows you entered are"} flagged to check${s.reconciles_with_flagged_flipped ? " (it adds up if they are flipped)" : ""}`
                  : ""}
              </li>
            ))}
          </ul>
          <Button
            type="button"
            size="sm"
            disabled={save.isPending}
            onClick={() => save.mutate()}
          >
            {save.isPending
              ? "Saving…"
              : `Change to ${typeLabel(proposal.account_type_after).toLowerCase()}`}
          </Button>
        </div>
      )}
      {flagged.map((s) => (
        <div
          key={s.source_document_id}
          className="space-y-1 rounded border border-dashed p-2"
        >
          <p>
            Statement {period(s)}: {s.flagged_rows.length}{" "}
            {s.flagged_rows.length === 1 ? "row was" : "rows were"} entered
            while this account had its previous type. Check{" "}
            {s.flagged_rows.length === 1 ? "it" : "them"} before flipping.
            {s.reconciles_with_flagged_flipped
              ? " The statement adds up if they are flipped."
              : s.reconciles_with_flagged_flipped === false
                ? " The statement still does not add up if they are flipped; check each row."
                : ""}
          </p>
          <ul>
            {s.flagged_rows.map((row) => (
              <li key={row.transaction_id}>
                {row.date || "Date not read"} ·{" "}
                {row.description || "No description"} ·{" "}
                {correctionMoney(row.amount_minor, s.currency || "")} ·{" "}
                {direction(row.direction)} → {direction(row.proposed_direction)}
              </li>
            ))}
          </ul>
          {canEdit && (
            <Button
              type="button"
              size="sm"
              variant="outline"
              disabled={flip.isPending}
              onClick={() => flip.mutate(s)}
            >
              Flip {s.flagged_rows.length}{" "}
              {s.flagged_rows.length === 1 ? "row" : "rows"}
            </Button>
          )}
        </div>
      ))}
      {notice && <p role="status">{notice}</p>}
      {failure && (
        <p role="alert">
          {failure instanceof Error ? failure.message : "The change failed."}{" "}
          Nothing was changed.
        </p>
      )}
    </div>
  )
}
