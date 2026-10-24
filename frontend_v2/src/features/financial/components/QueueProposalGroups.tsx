import { useState } from "react"
import { Button } from "@/components/ui/button"
import { confirmProposalGroup, type ProposalGroup } from "../lib/review-queue"

const FIELD_NAMES: Record<string, string> = {
  currency: "Currency",
  institution: "Bank",
  holder: "Account holder",
  account_number: "Account number",
}

/**
 * One confirmation per account: where the same proposed value applies to
 * several waiting statements of one account, a single click saves it on all of
 * them (empty fields only, as this person). Each statement is then checked
 * again; nothing is imported until it checks out.
 */
export function QueueProposalGroups({
  caseId,
  groups,
  fileIds,
  onDone,
  send = confirmProposalGroup,
}: {
  caseId: string
  groups: ProposalGroup[]
  fileIds: string[]
  onDone: (line: string) => void
  send?: typeof confirmProposalGroup
}) {
  const [busy, setBusy] = useState("")
  const [error, setError] = useState("")
  if (!groups.length) return null
  const confirm = async (group: ProposalGroup) => {
    setBusy(group.id)
    setError("")
    try {
      const result = await send(caseId, group, fileIds)
      onDone(
        `${FIELD_NAMES[group.field] ?? group.field} ${group.value} saved on ${result.saved} of ${group.statements} statements` +
          (result.failed ? ` (${result.failed} could not be saved: open them)` : "")
      )
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught))
    } finally {
      setBusy("")
    }
  }
  return (
    <section className="space-y-2 rounded border p-3 text-sm" aria-label="Confirm per account">
      <p className="font-medium">Confirm once per account</p>
      <ul className="space-y-1">
        {groups.map((group) => (
          <li key={group.id} className="flex flex-wrap items-center gap-2">
            <span>
              {FIELD_NAMES[group.field] ?? group.field} <strong>{group.value}</strong> for {group.statements} statements
              {group.account ? ` of account ${group.account}` : ""}
              {group.institution ? ` (${group.institution})` : ""}: {group.label}
            </span>
            <Button size="sm" variant="outline" disabled={!!busy} onClick={() => void confirm(group)}>
              {busy === group.id ? "Saving…" : `Confirm for all ${group.statements}`}
            </Button>
          </li>
        ))}
      </ul>
      {error && (
        <p role="alert" className="text-destructive">
          {error}
        </p>
      )}
    </section>
  )
}
