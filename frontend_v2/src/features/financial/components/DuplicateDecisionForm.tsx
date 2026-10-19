import { useFinancialAccess } from "../hooks/use-financial-access"
import { useEffect, useRef } from "react"
import { useFinancialDraft } from "../stores/financial-drafts"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { z } from "zod"
import { ApiError, fetchAPI } from "@/lib/api-client"
import { Button } from "@/components/ui/button"
import {
  duplicateRowsLabel,
  duplicateStatementLabel,
  type DuplicateStatementContext,
} from "../lib/duplicate-format"

export interface ReviewedDocument {
  document_id: string
  filename: string
  revision: string
  statement_context?: DuplicateStatementContext[]
  rows_by_status?: Record<string, number>
}
export interface DuplicateSelection {
  caseId: string
  document: ReviewedDocument
  primary?: ReviewedDocument
}
const answer = z.object({
  case_id: z.string(),
  document_id: z.string(),
  action: z.enum(["exclude", "restore"]),
  applied: z.literal(true),
  changed_rows: z.number().int().nonnegative(),
  adjudication_id: z.string().min(1),
})

function DuplicateDecisionFormForm({
  selection,
  onClose,
}: {
  selection: DuplicateSelection
  onClose: () => void
}) {
  const [reason, setReason, clearReason] = useFinancialDraft(
    selection.caseId,
    `duplicate-decision:${JSON.stringify([selection.document.document_id, selection.document.revision, selection.primary?.document_id, selection.primary?.revision])}`,
    ""
  )
  const lock = useRef(false)
  const heading = useRef<HTMLHeadingElement>(null)
  useEffect(() => {
    heading.current?.focus({ preventScroll: true })
    heading.current?.scrollIntoView({ block: "start" })
  }, [])
  const client = useQueryClient()
  const action = selection.primary ? "exclude" : "restore"
  const mutation = useMutation({
    retry: false,
    mutationFn: async ({
      selected,
      reason,
    }: {
      selected: DuplicateSelection
      reason: string
    }) => {
      const action = selected.primary ? "exclude" : "restore"
      const raw = await fetchAPI<unknown>(
        `/api/financial/documents/${encodeURIComponent(selected.document.document_id)}/duplicate-decision?${new URLSearchParams({ case_id: selected.caseId })}`,
        {
          method: "POST",
          body: {
            action,
            reason,
            expected_revision: selected.document.revision,
            ...(selected.primary
              ? {
                  primary_id: selected.primary.document_id,
                  expected_primary_revision: selected.primary.revision,
                }
              : {}),
          },
        }
      )
      const data = answer.parse(raw)
      if (
        data.case_id !== selected.caseId ||
        data.document_id !== selected.document.document_id ||
        data.action !== action
      )
        throw new Error("The response did not confirm the requested decision.")
      return data
    },
    onSettled: (_data, _error, variables) => {
      for (const prefix of [
        "financial-ledger",
        "financial-decisions",
        "ledger-source",
        "financial-linked-payments",
        "financial-proof-standing",
        "statement-import-status",
        "statement-import",
      ]) {
        void client.invalidateQueries({
          queryKey: [prefix, variables.selected.caseId],
        })
      }
    },
    onSuccess: () => clearReason(),
  })
  const refused =
    mutation.error instanceof ApiError &&
    [400, 401, 403, 404, 409, 422].includes(mutation.error.status)
  return (
    <form
      aria-label="Duplicate decision"
      className="space-y-3 rounded border p-4"
      onSubmit={(event) => {
        event.preventDefault()
        if (
          lock.current ||
          !reason.trim() ||
          mutation.isSuccess ||
          mutation.isError
        )
          return
        lock.current = true
        mutation.mutate(
          { selected: selection, reason },
          {
            onSettled: () => {
              lock.current = false
            },
          }
        )
      }}
    >
      <h3 ref={heading} tabIndex={-1} className="text-sm font-semibold">
        {action === "exclude"
          ? "Confirm duplicate exclusion"
          : "Restore excluded document"}
      </h3>
      <div className="grid gap-3 sm:grid-cols-2">
        <DecisionDocumentContext
          document={selection.document}
          label={action === "exclude" ? "Copy to exclude" : "Copy to restore"}
        />
        {selection.primary && (
          <DecisionDocumentContext
            document={selection.primary}
            label="Copy to keep"
          />
        )}
      </div>
      {selection.primary ? (
        <p className="text-sm">
          Keep: {selection.primary.filename}. Payments in the excluded copy will
          no longer count in Transactions or totals. Both original files and
          your reason stay available.
        </p>
      ) : (
        <p className="text-sm">
          Only payments removed by this duplicate decision will return to
          Transactions. Payments replaced by corrections or excluded for other
          reasons stay out. Both copies may then count.
        </p>
      )}
      <label className="block text-sm">
        Reason for this decision
        <textarea
          className="mt-1 block w-full rounded border bg-background p-2"
          required
          maxLength={4000}
          value={reason}
          disabled={
            mutation.isPending || mutation.isSuccess || mutation.isError
          }
          onChange={(event) => setReason(event.target.value)}
        />
      </label>
      {!mutation.isSuccess && (
        <p className="text-sm text-muted-foreground">
          Your explanation is kept in this browser tab for these document
          versions. Reopen the same comparison after refresh to continue.
        </p>
      )}
      {mutation.isSuccess && (
        <p role="status">
          Decision recorded. {mutation.data.changed_rows} payments{" "}
          {action === "exclude" ? "excluded" : "restored"}.
        </p>
      )}
      {mutation.isError && (
        <p role="alert">
          {refused
            ? `Decision refused: ${mutation.error.message}`
            : "The decision could not be confirmed. It may have been recorded. Check the refreshed comparison and decision history before trying again."}
        </p>
      )}
      <div className="flex flex-wrap gap-2">
        {!mutation.isSuccess && !mutation.isError && (
          <Button type="submit" disabled={!reason.trim() || mutation.isPending}>
            {mutation.isPending ? "Recording decision..." : "Record decision"}
          </Button>
        )}
        <Button
          type="button"
          variant="outline"
          disabled={mutation.isPending}
          onClick={onClose}
        >
          Close decision
        </Button>
      </div>
    </form>
  )
}

function DecisionDocumentContext({
  document,
  label,
}: {
  document: ReviewedDocument
  label: string
}) {
  return (
    <section
      aria-label={label}
      className="space-y-2 rounded border p-3 text-sm break-words"
    >
      <h4 className="font-semibold">
        {label}: {document.filename}
      </h4>
      <p>{duplicateRowsLabel(document.rows_by_status)}</p>
      {document.statement_context?.length ? (
        <ul className="space-y-1">
          {document.statement_context.map((period) => (
            <li key={period.period_id}>{duplicateStatementLabel(period)}</li>
          ))}
        </ul>
      ) : (
        <p>Saved statement account and period details are unavailable.</p>
      )}
    </section>
  )
}

export function DuplicateDecisionForm(
  props: Parameters<typeof DuplicateDecisionFormForm>[0]
) {
  const { canEdit } = useFinancialAccess()
  return canEdit ? (
    <DuplicateDecisionFormForm
      key={JSON.stringify(props.selection)}
      {...props}
    />
  ) : null
}
