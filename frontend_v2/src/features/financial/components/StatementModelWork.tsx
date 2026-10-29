import { useState } from "react"
import { useMutation } from "@tanstack/react-query"
import { z } from "zod"
import { fetchAPI } from "@/lib/api-client"
import { Button } from "@/components/ui/button"

/** A saved statement Claude saved or entered for a person, and whether a person has confirmed it. */
export const statementModelWork = z.object({
  status: z.enum(["not_confirmed", "confirmed", "corrected"]),
  model: z.string(),
  for_person: z.string().nullable().optional(),
  confirmed_by: z.string().nullable().optional(),
  confirmed_at: z.string().nullable().optional(),
  calls: z.array(
    z.object({
      id: z.string(),
      rule_id: z.string(),
      status: z.string(),
      summary: z.string(),
      resolved_by: z.string().nullable().optional(),
    })
  ),
})
export type StatementModelWork = z.infer<typeof statementModelWork>

export async function confirmStatement(caseId: string, sourceDocumentId: string) {
  return statementModelWork.parse(
    await fetchAPI(
      `/api/financial/judgements/statements/${encodeURIComponent(sourceDocumentId)}/confirm?${new URLSearchParams({ case_id: caseId })}`,
      { method: "POST", body: {} }
    )
  )
}

/**
 * The statement-level marker: "Saved by Claude for <person> · not confirmed", what Claude did, and one action that
 * confirms the whole statement as the person's. Nothing about the statement or its payments changes on confirm.
 */
export function StatementModelWorkMark({
  caseId,
  sourceDocumentId,
  work,
  canEdit,
  onConfirmed,
}: {
  caseId: string
  sourceDocumentId: string
  work: StatementModelWork
  canEdit: boolean
  onConfirmed: () => void
}) {
  const [open, setOpen] = useState(false)
  const confirm = useMutation({
    mutationFn: () => confirmStatement(caseId, sourceDocumentId),
    onSuccess: onConfirmed,
  })
  const person = work.for_person || "a person"
  if (work.status !== "not_confirmed")
    return (
      <p className="text-sm text-muted-foreground" data-testid="statement-model-work">
        Saved by {work.model} for {person}.{" "}
        {work.status === "corrected" ? "Corrected" : "Confirmed"} by {work.confirmed_by || "a person"}
        {work.confirmed_at ? ` on ${work.confirmed_at.slice(0, 10)}` : ""}.
      </p>
    )
  return (
    <div
      className="space-y-2 rounded border border-[#e7c66b] bg-[#fdf6dd] p-3 text-sm text-[#5c3d00] dark:bg-amber-950 dark:text-amber-100"
      role="group"
      aria-label="Saved by Claude, not confirmed"
      data-testid="statement-model-work"
    >
      <p>
        <strong>
          Saved by {work.model} for {person} · not confirmed
        </strong>
        . No person has checked these payments against the statement yet.
      </p>
      <button type="button" className="text-xs underline" aria-expanded={open} onClick={() => setOpen((v) => !v)}>
        {open ? "Hide what was done" : "What was done"}
      </button>
      {open && (
        <ul className="list-disc space-y-1 pl-5 text-xs">
          {work.calls.map((call) => (
            <li key={call.id}>{call.summary}</li>
          ))}
        </ul>
      )}
      {canEdit && (
        <div className="flex flex-wrap items-center gap-2">
          <Button size="sm" disabled={confirm.isPending} onClick={() => confirm.mutate()}>
            {confirm.isPending ? "Confirming…" : "I checked it against the statement: confirm"}
          </Button>
          <span className="text-xs">To correct a value, correct it on the payment first, then confirm.</span>
        </div>
      )}
      {confirm.isError && (
        <p role="alert" className="text-xs">
          {confirm.error.message}
        </p>
      )}
    </div>
  )
}
