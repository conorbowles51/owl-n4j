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
const values = z.object({
  holder: z.string(),
  institution: z.string(),
  account_number: z.string().optional(),
})
const relay = z
  .object({
    by: z.string(),
    note: z.string().nullish(),
    at: z.string().nullish(),
    via: z.string().nullish(),
    at_given: z.string().nullish(),
  })
  .passthrough()
const historyEntry = z.object({
  id: z.string(),
  kind: z.string(),
  at: z.string(),
  reason: z.string(),
  actor_name: z.string(),
  before: values,
  after: values,
  undone_at: z.string().optional(),
  // Set when Claude made the correction for a person (model work, services.financial.model_work).
  origin: z.object({ model: z.string(), for: z.object({ name: z.string().nullish() }).nullish() }).passthrough().nullish(),
  confirmed: z
    .object({
      by: z.string(),
      at: z.string(),
      basis: z.string(),
      // Set when someone else entered the confirmation on the person's instruction
      // (services.financial.relayed_confirmation): the confirmation is the person's, entered by them.
      relayed: relay.nullish(),
      later_relays: z.array(relay.extend({ basis: z.string().nullish() })).nullish(),
    })
    .passthrough()
    .nullish(),
})
const state = z.object({
  case_id: z.string(),
  account_id: z.string(),
  holder: z.string(),
  institution: z.string(),
  account_number: z.string(),
  account_clabe: z.string().optional(),
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
type HistoryEntry = z.infer<typeof historyEntry>
type Confirmation = NonNullable<HistoryEntry["confirmed"]>

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
/** "30 Oct 2026" from an ISO date or timestamp (UTC), or the text as given when it is not one. */
const dayOf = (value: string) => {
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(value)
  return match ? `${Number(match[3])} ${MONTHS[Number(match[2]) - 1]} ${match[1]}` : value
}

/** What changed in one correction, in words. */
const changeOf = (item: HistoryEntry) =>
  [
    item.before.holder !== item.after.holder ? `holder ${item.before.holder} → ${item.after.holder}` : "",
    item.before.institution !== item.after.institution
      ? `bank ${item.before.institution} → ${item.after.institution}`
      : "",
    item.after.account_number !== undefined && item.before.account_number !== item.after.account_number
      ? `account ${item.before.account_number} → ${item.after.account_number}`
      : "",
  ]
    .filter(Boolean)
    .join(", ") || "no change of value"

/** Who confirmed and, when someone else entered it on their instruction, who entered it and when. */
function confirmationLine(confirmed: Confirmation) {
  const relayed = confirmed.relayed
  if (!relayed)
    return `Confirmed by ${confirmed.by} on ${confirmed.at.slice(0, 10)}: ${confirmed.basis}`
  // A relay stored without a note does not say on whose instruction it was entered: shown as such, not assumed.
  const how = relayed.note ? `on ${confirmed.by}'s instruction` : "(no relay note recorded)"
  return `Confirmed by ${confirmed.by} · entered by ${relayed.by} ${how}, ${dayOf(relayed.at || confirmed.at)}: ${
    confirmed.basis
  }`
}

function RelayDetails({ confirmed }: { confirmed: Confirmation }) {
  const relays = [
    ...(confirmed.relayed ? [{ ...confirmed.relayed, basis: undefined as string | null | undefined }] : []),
    ...(confirmed.later_relays ?? []),
  ]
  if (!relays.length) return null
  return (
    <details className="text-xs text-muted-foreground">
      <summary className="cursor-pointer">
        How this confirmation was entered ({confirmed.by} did not press Confirm in Loupe)
      </summary>
      <ul className="list-disc pl-5">
        {relays.map((item, index) => (
          <li key={index}>
            Entered by {item.by}
            {item.at ? ` on ${dayOf(item.at)}` : ` on ${dayOf(confirmed.at)}`}
            {item.note ? `: ${item.note}` : ""}
            {item.via ? `. Instruction came by ${item.via}` : ""}
            {item.at_given ? `, given ${dayOf(item.at_given)}` : ""}
            {item.basis ? `. ${item.basis}` : ""}
          </li>
        ))}
      </ul>
    </details>
  )
}

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
  const [number, setNumber] = useState("")
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
    account_number: number.trim() || null,
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
      setNumber("")
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
      setNotice("Correction undone. The earlier account details are back.")
      void client.invalidateQueries()
    },
  })
  const confirm = useMutation({
    retry: false,
    mutationFn: async (correctionId: string) =>
      state.parse(
        await fetchAPI(`${base}/confirm?case_id=${encodeURIComponent(caseId)}`, {
          method: "POST",
          body: {
            expected_revision: query.data!.revision,
            correction_id: correctionId,
            basis: reason,
          },
        })
      ),
    onSuccess: (result) => {
      client.setQueryData(key, result)
      setNotice("Correction confirmed as yours. Claude's correction stays in the account history.")
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
  const failure = review.error || save.error || undo.error || confirm.error
  const latest = [...data.history]
    .reverse()
    .find((item) => item.kind === "correction" && !item.undone_at)
  // Every correction Claude made that stands, each with its own confirmation (the latest is not the only one).
  const byModel = data.history.filter((item) => item.kind === "correction" && !item.undone_at && item.origin)
  const ready =
    reason.trim() !== "" &&
    ((holder.trim() !== "" && holder.trim() !== data.holder) ||
      (institution.trim() !== "" && institution.trim() !== data.institution) ||
      (number.trim() !== "" && number.trim() !== data.account_number))
  return (
    <section
      aria-label="Account holder, bank and number"
      className="space-y-2 rounded border p-3 text-sm"
    >
      <h3 className="font-semibold">Account holder, bank and number</h3>
      <p>
        <span className="font-medium">
          {data.holder || "Holder not recorded"}
        </span>
        {data.institution ? ` · ${data.institution}` : ""}
        {data.account_number ? ` · ${data.account_number}` : ""}
        {data.account_clabe ? ` · CLABE ${data.account_clabe}` : ""} ·{" "}
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
            Account number as printed (not the CLABE; a CLABE saved as the
            number is kept with the account)
            <input
              className="rounded border bg-background p-1"
              value={number}
              placeholder={data.account_number}
              onChange={(event) => {
                setNumber(event.target.value)
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
            {proposal.after.account_number !== undefined &&
            proposal.before.account_number !== proposal.after.account_number
              ? ` · account ${proposal.before.account_number || "not recorded"} → ${proposal.after.account_number}`
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
            Last corrected by {latest.origin ? `${latest.origin.model} for ${latest.origin.for?.name || "a person"}` : latest.actor_name}:{" "}
            {latest.before.holder} → {latest.after.holder}
            {latest.after.account_number !== undefined &&
            latest.before.account_number !== latest.after.account_number
              ? `, account ${latest.before.account_number} → ${latest.after.account_number}`
              : ""}
            . Reason: {latest.reason}
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
      {byModel.length > 0 && (
        <ul className="space-y-2" aria-label={`Corrections ${byModel[0].origin!.model} made`}>
          {byModel.map((item) => (
            <li key={item.id} className="space-y-1">
              <p>
                {item.origin!.model} for {item.origin!.for?.name || "a person"} on {dayOf(item.at)}: {changeOf(item)}.
              </p>
              {item.confirmed ? (
                <>
                  <p>{confirmationLine(item.confirmed)}</p>
                  <RelayDetails confirmed={item.confirmed} />
                </>
              ) : (
                <p>
                  <strong>Corrected by {item.origin!.model} · not confirmed.</strong> A person confirms it after
                  checking the statement.
                </p>
              )}
              {canEdit && !item.confirmed && (
                <Button
                  type="button"
                  size="sm"
                  disabled={confirm.isPending || !reason.trim()}
                  title={reason.trim() ? undefined : "Enter what you checked first"}
                  onClick={() => confirm.mutate(item.id)}
                >
                  Confirm this correction (say what you checked above)
                </Button>
              )}
            </li>
          ))}
        </ul>
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
