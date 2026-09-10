import { StatementScopeEditor } from "./StatementScopeEditor"
import {
  statementScope,
  scopeReading,
  type StatementScope,
} from "../lib/statement-scope-contract"
import { useRef, useState } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { z } from "zod"
import { Button } from "@/components/ui/button"
import { fetchAPI } from "@/lib/api-client"
import { assertCandidateScope, candidateUrl } from "../lib/candidate-contract"
import { LedgerSourceDialog } from "./LedgerSourceDialog"

const id = z.string().min(1)
const revision = z.string().regex(/^[a-f0-9]{64}$/)
const readySchema = z.object({
  case_id: id,
  evidence_file_id: id,
  applied: z.literal(false),
  revision,
  statement_scopes: z.array(statementScope).max(16).optional(),
  readings: z.array(scopeReading).max(1000).optional(),
  unbound_statement_dates: z.number().int().nonnegative().optional(),
  resolved_count: z.number().int().min(1).max(1000),
  rejected_count: z.number().int().min(0).max(1000),
  proof_class: z.literal("p3"),
  included_in_default_totals: z.literal(false),
  file_bytes_verified: z.literal(true),
  source_sha256: revision,
  byte_count: z.number().int().nonnegative(),
  limitation: z.string(),
})
const receiptSchema = z
  .object({
    case_id: id,
    evidence_file_id: id,
    applied: z.literal(true),
    created: z.boolean(),
    finalization_id: id,
    finalization_revision: revision,
    source_document_id: id,
    run_id: id,
    transaction_count: z.number().int().min(1).max(1000),
    transactions: z
      .array(
        z.object({
          candidate_id: id,
          transaction_id: id,
          ref_id: id,
          superseded_by_id: id.nullable(),
        })
      )
      .max(1000),
    proof_class_at_finalization: z.literal("p3"),
    included_in_default_totals: z.literal(false),
    limitation: z.string(),
  })
  .superRefine((value, context) => {
    if (
      value.transactions.length !== value.transaction_count ||
      new Set(value.transactions.map((row) => row.transaction_id)).size !==
        value.transaction_count ||
      new Set(value.transactions.map((row) => row.candidate_id)).size !==
        value.transaction_count
    )
      context.addIssue({
        code: "custom",
        message: "Finalization links do not match the transaction count.",
      })
  })
const previewSchema = z.union([readySchema, receiptSchema])

export function CandidateFinalizationPanel(props: {
  caseId: string
  fileId: string
}) {
  return <Finalization key={`${props.caseId}:${props.fileId}`} {...props} />
}
function Finalization({ caseId, fileId }: { caseId: string; fileId: string }) {
  const client = useQueryClient()
  const lock = useRef(false)
  const [blocked, setBlocked] = useState(false)
  const [documentary, setDocumentary] = useState(false)
  const [coverage, setCoverage] = useState(false)
  const [reason, setReason] = useState("")
  const [source, setSource] = useState<string | null>(null)
  const [statementScopes, setStatementScopes] = useState<StatementScope[]>([])
  const [editingStatement, setEditingStatement] = useState(false)
  function scoped<T extends { case_id: string; evidence_file_id: string }>(
    data: T
  ) {
    assertCandidateScope(data, caseId)
    if (data.evidence_file_id !== fileId)
      throw new Error(
        "The result belongs to a different PDF. Reload the preview."
      )
    return data
  }
  const preview = useMutation({
    retry: false,
    mutationFn: async () => {
      const data = scoped(
        previewSchema.parse(
          await fetchAPI<unknown>(
            candidateUrl(
              `candidate-sources/${encodeURIComponent(fileId)}/finalization-preview`,
              caseId
            ),
            statementScopes.length
              ? { method: "POST", body: { statement_scopes: statementScopes } }
              : undefined
          )
        )
      )
      if (
        !data.applied &&
        JSON.stringify(data.statement_scopes ?? []) !==
          JSON.stringify(
            statementScopes.map((value) => statementScope.parse(value))
          )
      )
        throw new Error(
          "The preview does not match the reviewed statement controls."
        )
      return data
    },
  })
  const finalize = useMutation({
    retry: false,
    mutationFn: async () => {
      const data = preview.data
      if (!data || data.applied || !documentary || !coverage || !reason.trim())
        throw new Error(
          "Load a current preview and complete both confirmations and the reason."
        )
      const result = scoped(
        receiptSchema.parse(
          await fetchAPI<unknown>(
            candidateUrl(
              `candidate-sources/${encodeURIComponent(fileId)}/finalize`,
              caseId
            ),
            {
              method: "POST",
              body: {
                expected_revision: data.revision,
                documentary_financial_rows: documentary,
                accept_incomplete_coverage: coverage,
                reason,
                ...(statementScopes.length
                  ? { statement_scopes: statementScopes }
                  : {}),
              },
            }
          )
        )
      )
      if (
        result.finalization_revision !== data.revision ||
        result.transaction_count !== data.resolved_count
      )
        throw new Error(
          "The returned finalization does not match this preview. Reload before continuing."
        )
      return result
    },
    onSettled: () => {
      setBlocked(true)
      for (const prefix of [
        "financial-candidates",
        "financial-ledger",
        "financial-runs",
        "financial-proof-standing",
        "financial-decisions",
      ])
        void client.invalidateQueries({ queryKey: [prefix, caseId] })
    },
  })
  const receipt = finalize.data ?? (preview.data?.applied ? preview.data : null)
  const ready = preview.data && !preview.data.applied ? preview.data : null
  return (
    <section
      aria-label="Finalize reviewed PDF rows"
      className="space-y-3 rounded border p-3"
    >
      <h3 className="font-semibold">Finalize reviewed rows</h3>
      <p>
        Check all saved batches from this PDF before creating ledger
        transactions. Every reading must be resolved or rejected.
      </p>
      <p className="text-muted-foreground">
        Selected rows stay P3 and outside default verified totals. Finalizing
        seals this PDF reading: no later additions or candidate edits. Changes
        to written rows use ledger corrections.
      </p>
      <Button
        variant="outline"
        disabled={preview.isPending || finalize.isPending}
        onClick={() => {
          preview.reset()
          finalize.reset()
          lock.current = false
          setBlocked(false)
          setDocumentary(false)
          setCoverage(false)
          setReason("")
          preview.mutate()
        }}
      >
        {preview.data || blocked || preview.isError
          ? "Reload finalization preview"
          : "Preview finalization"}
      </Button>
      {statementScopes.length > 0 && !receipt && (
        <div className="space-y-2">
          <p>
            {statementScopes.length} reviewed statement definitions. Reload the
            preview after any change.
          </p>
          {statementScopes.map((scope, index) => (
            <div key={index} className="flex flex-wrap items-center gap-2">
              <span>
                {scope.start.value} to {scope.end.value} · {scope.currency} ·{" "}
                {scope.candidate_ids.length} rows
              </span>
              <Button
                variant="outline"
                disabled={finalize.isPending || blocked}
                onClick={() => {
                  setStatementScopes((v) => v.filter((_, i) => i !== index))
                  preview.reset()
                  setDocumentary(false)
                  setCoverage(false)
                }}
              >
                Remove statement {index + 1}
              </Button>
            </div>
          ))}
        </div>
      )}
      {preview.isPending && (
        <p role="status">Checking saved reviews and source bytes…</p>
      )}
      {preview.isError && (
        <p role="alert">
          Finalization preview unavailable. {preview.error.message}
        </p>
      )}
      {ready && !receipt && (
        <div className="space-y-3">
          <p>
            {ready.unbound_statement_dates
              ? `${ready.unbound_statement_dates} undated readings need matching printed statement end controls before finalization. `
              : ""}
            {ready.resolved_count} resolved rows will become transactions;{" "}
            {ready.rejected_count} rejected readings stay in history. This count
            does not establish complete PDF coverage.
          </p>
          {ready.readings &&
            !blocked &&
            !finalize.isPending &&
            statementScopes.length < 16 &&
            (editingStatement ? (
              <StatementScopeEditor
                caseId={caseId}
                fileId={fileId}
                readings={ready.readings.filter(
                  (row) =>
                    !statementScopes.some((scope) =>
                      scope.candidate_ids.includes(row.candidate_id)
                    )
                )}
                onClose={() => setEditingStatement(false)}
                onSave={(scope) => {
                  setStatementScopes((v) => [...v, scope])
                  setEditingStatement(false)
                  preview.reset()
                  setDocumentary(false)
                  setCoverage(false)
                }}
              />
            ) : (
              <Button
                variant="outline"
                onClick={() => setEditingStatement(true)}
              >
                Add printed statement controls
              </Button>
            ))}
          <fieldset
            disabled={blocked || finalize.isPending || editingStatement}
            className="space-y-3"
          >
            <label className="flex items-start gap-2">
              <input
                type="checkbox"
                checked={documentary}
                onChange={(e) => setDocumentary(e.target.checked)}
              />
              These are documentary financial rows, not amounts asserted in
              letters or other narrative.
            </label>
            <label className="flex items-start gap-2">
              <input
                type="checkbox"
                checked={coverage}
                onChange={(e) => setCoverage(e.target.checked)}
              />
              I accept incomplete document coverage and understand that
              finalizing prevents later additions to this reading.
            </label>
            <label className="block">
              Reason for finalization
              <textarea
                aria-label="Reason for finalization"
                className="block w-full rounded border bg-background p-2"
                value={reason}
                maxLength={4096}
                onChange={(e) => setReason(e.target.value)}
              />
            </label>
            <Button
              disabled={
                !documentary ||
                !coverage ||
                !reason.trim() ||
                Boolean(ready.unbound_statement_dates)
              }
              onClick={() => {
                if (lock.current || blocked || finalize.isPending) return
                lock.current = true
                finalize.mutate()
              }}
            >
              Finalize selected rows
            </Button>
          </fieldset>
        </div>
      )}
      {finalize.isPending && <p role="status">Finalizing reviewed rows…</p>}
      {finalize.isError && (
        <p role="alert">
          Finalization could not be confirmed. {finalize.error.message} Reload
          the preview before another attempt.
        </p>
      )}
      {receipt && (
        <div className="space-y-2" role="status">
          <p>
            Finalized {receipt.transaction_count} transactions. Original
            readings and review history are retained. These P3 rows remain
            outside default verified totals.
          </p>
          <ul>
            {receipt.transactions.map((row) => (
              <li key={row.transaction_id}>
                <Button
                  variant="link"
                  onClick={() => setSource(row.transaction_id)}
                >
                  View source: {row.ref_id}
                </Button>
                {row.superseded_by_id && (
                  <span> — original reading has a later correction</span>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
      {source && (
        <LedgerSourceDialog
          caseId={caseId}
          transactionId={source}
          onClose={() => setSource(null)}
        />
      )}
    </section>
  )
}
