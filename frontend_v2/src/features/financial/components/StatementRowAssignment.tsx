import { useState } from "react"
import { useMutation } from "@tanstack/react-query"
import { z } from "zod"
import { fetchAPI } from "@/lib/api-client"
import { Button } from "@/components/ui/button"
import type { StatementSection } from "./StatementSectionPicker"

const checks = z.object({
  transaction_count: z.number(),
  checks: z.array(
    z.object({
      kind: z.string(),
      status: z.enum(["matches", "difference", "unavailable"]),
    })
  ),
})
const resultSchema = z.object({
  case_id: z.string(),
  evidence_file_id: z.string(),
  revision: z.string(),
  applied: z.boolean(),
  moved_rows: z.number(),
  affected_reviews: z.number(),
  statements: z.array(
    z.object({
      statement_id: z.string(),
      label: z.string(),
      before: checks,
      after: checks,
    })
  ),
})
const names: Record<string, string> = {
  closing_balance: "Closing balance",
  running_balance: "Running balances",
  credit_total: "Printed credit total",
  debit_total: "Printed debit total",
  fee_total: "Printed fee total",
  interest_total: "Printed interest total",
}
const status = {
  matches: "Matches",
  difference: "Difference to check",
  unavailable: "Unavailable",
}

export function StatementRowAssignment({
  caseId,
  fileId,
  choices,
  request,
  rowIds,
  reason,
  reviewRevision,
  batchId,
  onApplied,
  onBusy,
}: {
  caseId: string
  fileId: string
  choices: StatementSection[]
  request: unknown
  rowIds: string[]
  reason: string
  reviewRevision: string
  batchId?: string
  onApplied: () => Promise<void>
  onBusy?: (busy: boolean) => void
}) {
  const [target, setTarget] = useState("")
  const [search, setSearch] = useState("")
  const [previewPayload, setPreviewPayload] = useState("")
  const payload = JSON.stringify({
    request,
    target_statement_id: target,
    row_ids: [...rowIds].sort(),
    reason,
    expected_review_revision: reviewRevision,
    batch_id: batchId ?? null,
  })
  const run = async (apply: boolean) => {
    const result = resultSchema.parse(
      await fetchAPI(
        `/api/financial/statement-import/${fileId}/row-assignment/${apply ? "apply" : "preview"}?case_id=${caseId}`,
        {
          method: "POST",
          body: {
            ...JSON.parse(payload),
            ...(apply ? { expected_preview: preview.data?.revision } : {}),
          },
          timeout: 120000,
        }
      )
    )
    if (
      result.case_id !== caseId ||
      result.evidence_file_id !== fileId ||
      result.applied !== apply ||
      result.moved_rows !== rowIds.length
    )
      throw Error(
        "The move result does not match this statement selection. Reopen the review to check it."
      )
    return result
  }
  const preview = useMutation({
    retry: false,
    mutationFn: async () => {
      setPreviewPayload(payload)
      return run(false)
    },
  })
  const save = useMutation({
    retry: false,
    mutationFn: async () => {
      onBusy?.(true)
      try {
        const result = await run(true)
        await onApplied()
        return result
      } finally {
        onBusy?.(false)
      }
    },
  })
  const stale = !!preview.data && previewPayload !== payload
  const visible = choices.filter(
    (choice) =>
      `${choice.institution} ${choice.account_reference} ${choice.period_start} ${choice.period_end}`
        .toLowerCase()
        .includes(search.toLowerCase()) || choice.id === target
  )
  return (
    <div
      role="region"
      className="space-y-3 rounded border bg-background p-3"
      aria-label="Move transactions to another statement"
    >
      <p className="text-sm">
        Move the selected transactions to another recognised account or period
        in this PDF. Their original PDF locations and corrected values are kept.
        Both statements are saved and checked again.
      </p>
      {choices.length > 10 && (
        <label className="block text-sm">
          Find an account or period
          <input
            className="block border rounded p-2 mt-1 bg-background"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </label>
      )}
      <label className="block text-sm">
        Move to account and period
        <select
          aria-label="Move to account and period"
          className="block w-full border rounded bg-background p-2 mt-1"
          value={target}
          onChange={(e) => setTarget(e.target.value)}
          disabled={save.isPending}
        >
          <option value="">Choose a statement</option>
          {visible.map((choice) => (
            <option key={choice.id} value={choice.id}>
              {choice.institution} · {choice.account_reference} ·{" "}
              {choice.period_start} to {choice.period_end}
            </option>
          ))}
        </select>
      </label>
      <Button
        size="sm"
        variant="outline"
        disabled={
          !target ||
          !rowIds.length ||
          !reason.trim() ||
          preview.isPending ||
          save.isPending
        }
        onClick={() => preview.mutate()}
      >
        {preview.isPending ? "Checking both statements…" : "Preview move"}
      </Button>
      {(preview.error || save.error) && (
        <p role="alert" className="text-sm">
          {(preview.error || save.error)?.message}
        </p>
      )}
      {stale && (
        <p role="alert" className="text-sm">
          The selection or values changed. Preview the move again.
        </p>
      )}
      {preview.data && !stale && (
        <div className="space-y-3">
          <p className="text-sm font-medium">
            {preview.data.moved_rows}{" "}
            {preview.data.moved_rows === 1 ? "transaction" : "transactions"}{" "}
            will move. Existing saved corrections are kept in both statements.
          </p>
          {preview.data.statements.map((statement, index) => (
            <div
              key={statement.statement_id}
              className="rounded border p-3 text-sm"
            >
              <p className="font-medium">
                {index === 0 ? "From" : "To"}: {statement.label}
              </p>
              <p>
                {statement.before.transaction_count}{" "}
                {statement.before.transaction_count === 1
                  ? "transaction"
                  : "transactions"}{" "}
                before; {statement.after.transaction_count} after.
              </p>
              <table
                className="w-full mt-2"
                aria-label={`${index === 0 ? "Source" : "Destination"} statement checks`}
              >
                <thead>
                  <tr>
                    <th className="text-left">Check</th>
                    <th className="text-left">Before</th>
                    <th className="text-left">After</th>
                  </tr>
                </thead>
                <tbody>
                  {statement.after.checks.map((check) => (
                    <tr key={check.kind}>
                      <td>{names[check.kind] ?? check.kind}</td>
                      <td>
                        {
                          status[
                            statement.before.checks.find(
                              (old) => old.kind === check.kind
                            )?.status ?? "unavailable"
                          ]
                        }
                      </td>
                      <td>{status[check.status]}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ))}
          <p className="text-sm">
            This saves the move and your current corrections. It does not import
            payments. Any remaining differences stay flagged for review.
          </p>
          <Button
            disabled={save.isPending || preview.isPending}
            onClick={() => save.mutate()}
          >
            {save.isPending
              ? "Saving move…"
              : `Save move of ${preview.data.moved_rows} ${preview.data.moved_rows === 1 ? "transaction" : "transactions"}`}
          </Button>
        </div>
      )}
    </div>
  )
}
