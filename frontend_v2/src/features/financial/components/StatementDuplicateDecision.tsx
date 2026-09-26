import { useEffect, useId, useRef, useState } from "react"
import { useMutation } from "@tanstack/react-query"
import { Button } from "@/components/ui/button"
import { DocumentViewer } from "@/components/ui/document-viewer"
import { evidenceAPI } from "@/features/evidence/api"
import { ApiError, fetchAPI } from "@/lib/api-client"
import {
  statementDuplicateResponse,
  type RetainedStatement,
  type StatementDuplicateDisposition,
} from "../lib/statement-duplicate"

export interface StatementDuplicateDecisionProps {
  caseId: string
  fileId: string
  statementId?: string | null
  currency?: string | null
  readingRevision: string
  decision?: StatementDuplicateDisposition | null
  canEdit: boolean
  matchingStatement?: boolean
  canCheck?: boolean
  checkDisabledReason?: string
  onDecision: (updated: StatementDuplicateDisposition) => void
  onBusy?: (busy: boolean) => void
  onOpenRetained?: (retained: RetainedStatement) => void
}

const fields: Record<string, string> = {
  bank: "Bank",
  full_account_number: "Full account number",
  account_holder: "Account holder",
  period_start: "Start date",
  period_end: "End date",
  currency: "Currency",
  account_type: "Account type",
}

const titles: Record<StatementDuplicateDisposition["status"], string> = {
  ignored: "Duplicate - Ignored by system",
  retained: "Retained statement",
  not_duplicate: "No confirmed duplicate",
  needs_comparison: "Compare this statement",
  restored: "Restored for review",
}

function StatementDuplicateDecisionView({
  caseId,
  fileId,
  statementId,
  currency,
  readingRevision,
  decision,
  canEdit,
  canCheck = true,
  matchingStatement = false,
  checkDisabledReason,
  onDecision,
  onBusy,
  onOpenRetained,
}: StatementDuplicateDecisionProps) {
  const [current, setCurrent] = useState(decision)
  const [source, setSource] = useState<RetainedStatement | null>(null)
  const [reason, setReason] = useState("")
  const lock = useRef(false)
  const releaseBusy = useRef<(() => void) | null>(null)
  const disabledReasonId = useId()
  useEffect(
    () => () => {
      lock.current = false
      const release = releaseBusy.current
      releaseBusy.current = null
      release?.()
    },
    []
  )
  const mutation = useMutation({
    retry: false,
    mutationFn: async (action: "check" | "restore" | "ignore") => {
      const response = await fetchAPI<unknown>(
        `/api/financial/statement-import/${encodeURIComponent(fileId)}/duplicate-disposition?${new URLSearchParams({ case_id: caseId })}`,
        {
          method: "POST",
          body: {
            action,
            expected_reading_revision: readingRevision,
            statement_id: statementId || null,
            currency: currency || null,
            ...(action === "restore"
              ? {
                  expected_decision_revision: current?.revision,
                  reason: reason.trim(),
                }
              : {}),
          },
        }
      )
      const parsed = statementDuplicateResponse.safeParse(response)
      if (
        !parsed.success ||
        parsed.data.case_id !== caseId ||
        parsed.data.evidence_file_id !== fileId ||
        (parsed.data.statement_id || null) !== (statementId || null) ||
        parsed.data.duplicate_disposition.reading_revision !==
          readingRevision ||
        !parsed.data.duplicate_disposition.current
      )
        throw new Error(
          "The response could not be verified for this statement. Reopen this period to check the saved decision."
        )
      return parsed.data.duplicate_disposition
    },
  })
  const stale =
    !!current &&
    (!current.current || current.reading_revision !== readingRevision)
  const ignored = current?.status === "ignored" && !stale
  const requiresReopen =
    mutation.error instanceof ApiError &&
    [401, 403, 404, 409].includes(mutation.error.status)
  const retained = current?.retained
  const checkable =
    !current ||
    stale ||
    ["needs_comparison", "not_duplicate"].includes(current.status) ||
    mutation.isError

  function act(action: "check" | "restore" | "ignore") {
    if (lock.current || !canEdit || requiresReopen) return
    if ((action === "check" || action === "ignore") && !canCheck) return
    if (action === "restore" && !ignored) return
    lock.current = true
    releaseBusy.current = () => onBusy?.(false)
    onBusy?.(true)
    mutation.mutate(action, {
      // Per-call callbacks do not run after this scoped panel unmounts.
      onSuccess: (updated) => {
        setCurrent(updated)
        setReason("")
        onDecision(updated)
      },
      onSettled: () => {
        lock.current = false
        const release = releaseBusy.current
        releaseBusy.current = null
        release?.()
      },
    })
  }

  return (
    <section
      aria-label="Statement duplicate decision"
      className="min-w-0 space-y-3 rounded border border-amber-300 bg-amber-50/40 p-3 text-sm dark:bg-amber-950/20"
    >
      <h3 className="font-semibold">
        {stale
          ? titles.needs_comparison
          : current
            ? current.basis === "investigator_decision" &&
              current.status === "ignored"
              ? "Duplicate — left unimported"
              : titles[current.status]
            : "Check for a duplicate statement"}
      </h3>
      <p>
        {stale
          ? "The reading or saved decision changed. Check these statements again before relying on the earlier decision."
          : current?.reason ||
            "Compare this statement’s bank, full account number, holder, currency and period with existing statements. Matching contents establish a duplicate."}
      </p>
      {current?.matched_fields.length ? (
        <p className="text-muted-foreground">
          {stale ? "Earlier matching details" : "Matching details"}:{" "}
          {current.matched_fields
            .map((field) => fields[field] || field.replaceAll("_", " "))
            .join(", ")}
          .
        </p>
      ) : null}
      {current?.basis === "identical_bytes" && (
        <p>
          {stale
            ? "The earlier comparison found matching original file contents."
            : "The original file contents match."}
        </p>
      )}
      {current?.basis === "identical_financial_reading" && (
        <p>
          {stale
            ? "The earlier comparison found matching extracted payments and balances."
            : "The extracted payments and balances match."}
        </p>
      )}
      {retained && (
        <div className="min-w-0 space-y-2 rounded border bg-background p-3">
          <p className="break-words">
            {current?.status === "needs_comparison" || stale
              ? "Statement to compare"
              : "Retained statement"}
            : <strong>{retained.filename}</strong>
            {retained.source_document_id
              ? " · Already imported"
              : " · Statement reading retained"}
          </p>
          <div className="flex flex-wrap gap-2">
            <Button
              type="button"
              size="sm"
              variant="outline"
              onClick={() => setSource(retained)}
            >
              Open retained original
            </Button>
            {onOpenRetained && (
              <Button
                type="button"
                size="sm"
                variant="outline"
                onClick={() => onOpenRetained(retained)}
              >
                Open retained statement review
              </Button>
            )}
          </div>
        </div>
      )}
      {ignored && (
        <p>
          This copy is excluded from new imports. Its evidence and saved
          corrections remain available.
        </p>
      )}
      {current?.status === "restored" && !stale && (
        <p>
          Compare both statements and resolve the review checks before
          importing. Restoring this copy does not add transactions or mark it
          ready.
        </p>
      )}
      {canEdit && ignored && (
        <div className="space-y-2">
          <label className="block">
            Reason for restoring to review (optional)
            <textarea
              className="mt-1 block w-full rounded border bg-background p-2"
              value={reason}
              maxLength={4096}
              disabled={mutation.isPending || requiresReopen}
              onChange={(event) => setReason(event.target.value)}
            />
          </label>
          <Button
            type="button"
            size="sm"
            variant="outline"
            disabled={mutation.isPending || requiresReopen}
            onClick={() => act("restore")}
          >
            {mutation.isPending && mutation.variables === "restore"
              ? "Restoring…"
              : "Restore for comparison"}
          </Button>
        </div>
      )}
      {canEdit && !ignored && (matchingStatement || (current?.status === "needs_comparison" && retained)) && (
        <div className="space-y-2">
          <Button
            type="button"
            variant="outline"
            disabled={!canCheck || mutation.isPending || requiresReopen}
            onClick={() => act("ignore")}
          >
            {mutation.isPending && mutation.variables === "ignore"
              ? "Saving decision…"
              : "Don’t import this duplicate"}
          </Button>
          <p>
            The file and saved corrections stay available. You can restore this
            statement for comparison later.
          </p>
        </div>
      )}
      {canEdit && checkable && (
        <div className="space-y-2">
          <Button
            type="button"
            size="sm"
            variant="outline"
            disabled={!canCheck || mutation.isPending || requiresReopen}
            aria-describedby={!canCheck ? disabledReasonId : undefined}
            onClick={() => act("check")}
          >
            {mutation.isPending && mutation.variables === "check"
              ? "Checking duplicates…"
              : "Check duplicate status"}
          </Button>
          {!canCheck && (
            <p id={disabledReasonId} className="text-muted-foreground">
              {checkDisabledReason ||
                "Save your changes before checking for duplicates."}
            </p>
          )}
        </div>
      )}
      {mutation.isSuccess && (
        <p role="status">
          {mutation.variables === "restore"
            ? "Restored for comparison. No transactions were imported."
            : mutation.variables === "ignore"
              ? "Left unimported. You can restore it for comparison here."
              : "Duplicate check saved."}
        </p>
      )}
      {mutation.isError && (
        <p role="alert" className="text-destructive">
          {mutation.error instanceof ApiError ||
          mutation.error.message.includes("could not be verified")
            ? mutation.error.message
            : "The result could not be confirmed. Reopen this statement to check its saved duplicate decision before trying again."}
        </p>
      )}
      {!canEdit && (
        <p className="text-muted-foreground">
          You can inspect the statements. Editing access is required to check or
          restore a duplicate decision.
        </p>
      )}
      {source && (
        <DocumentViewer
          caseId={caseId}
          evidenceId={source.evidence_file_id}
          documentName={source.filename}
          initialPage={source.page_number}
          documentUrl={evidenceAPI.getFileUrl(source.evidence_file_id)}
          navigationKey={`${caseId}:${source.evidence_file_id}:${source.statement_id || ""}`}
          open
          onOpenChange={(open) => {
            if (!open) setSource(null)
          }}
        />
      )}
    </section>
  )
}

export function StatementDuplicateDecision(
  props: StatementDuplicateDecisionProps
) {
  return (
    <StatementDuplicateDecisionView
      key={JSON.stringify([
        props.caseId,
        props.fileId,
        props.statementId,
        props.currency,
        props.readingRevision,
        props.decision?.revision,
        props.decision?.status,
        props.decision?.current,
      ])}
      {...props}
    />
  )
}
