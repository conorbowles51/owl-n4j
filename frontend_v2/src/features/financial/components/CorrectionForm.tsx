import { useFinancialAccess } from "../hooks/use-financial-access"
import type { LedgerTransaction } from "../api"
import { NativeControlComparisonPanel } from "./NativeControlComparisonPanel"
import { PrintedTotalChecks } from "./PrintedTotalChecks"
import { useRef, useState } from "react"
import { useFinancialDraft } from "../stores/financial-drafts"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { ApiError, fetchAPI } from "@/lib/api-client"
import { RunningBalanceComparisonPanel } from "./RunningBalanceComparisonPanel"
import { Button } from "@/components/ui/button"
import {
  correctionAnswer,
  correctionMinor,
  correctionMoney,
  correctionPreview,
  type CorrectionPreview,
} from "../lib/correction-contract"

function CorrectionFormForm({
  caseId,
  transactionId,
  currency,
  initialDirection = "credit",
  initialRow,
  onClose,
}: {
  caseId: string
  transactionId: string
  currency: string
  initialDirection?: "credit" | "debit"
  initialRow?: LedgerTransaction
  onClose: () => void
}) {
  const editAmount = (value: string | number | null) =>
    value === null
      ? ""
      : correctionMoney(String(value), currency).replace(` ${currency}`, "")
  const fieldLabels = {
    transaction_date: "Transaction date",
    posted_date: "Booking date",
    value_date: "Value date",
    effective_date: "Effective date",
    description: "Description",
    counterparty_raw: "Counterparty as printed",
    bank_reference: "Bank reference",
    transaction_type: "Transaction type",
  } as const
  const [savedDraft, setDraft, clearDraft] = useFinancialDraft(
    caseId,
    `transaction-correction:${transactionId}:${currency}`,
    {
      amount: initialRow ? editAmount(initialRow.amount_minor) : "",
      direction: initialDirection,
      reason: "",
      balance: initialRow ? editAmount(initialRow.running_balance_minor) : "",
      editedFields: Object.fromEntries(
        Object.keys(fieldLabels).map((key) => [
          key,
          initialRow?.[key as keyof typeof fieldLabels] ?? "",
        ])
      ) as Record<string, string>,
    }
  )
  const [completedDraft, setCompletedDraft] = useState<
    typeof savedDraft | null
  >(null)
  const { amount, direction, reason, balance, editedFields } =
    completedDraft ?? savedDraft
  const balanceMagnitude = correctionMinor(balance.replace(/^-/, ""), currency)
  const balanceMinor =
    balance === ""
      ? null
      : balanceMagnitude === null
        ? undefined
        : `${balance.startsWith("-") && balanceMagnitude !== "0" ? "-" : ""}${balanceMagnitude}`
  const fieldChanges: Record<string, string | null> = {}
  if (initialRow) {
    for (const key of Object.keys(fieldLabels) as Array<
      keyof typeof fieldLabels
    >) {
      if (editedFields[key] !== (initialRow[key] ?? ""))
        fieldChanges[key] = editedFields[key] || null
    }
    if (
      balanceMinor !== undefined &&
      balanceMinor !==
        (initialRow.running_balance_minor === null
          ? null
          : String(initialRow.running_balance_minor))
    )
      fieldChanges.running_balance_minor = balanceMinor
  }
  const lock = useRef(false)
  const client = useQueryClient()
  const minor = correctionMinor(amount, currency)
  const path = `/api/financial/transactions/${encodeURIComponent(transactionId)}`
  const preview = useMutation({
    retry: false,
    mutationFn: async (input: {
      amount_minor: string
      direction: "credit" | "debit"
      fields?: Record<string, string | null>
    }) => {
      const data = correctionPreview.parse(
        await fetchAPI<unknown>(
          `${path}/correction-preview?${new URLSearchParams({ case_id: caseId })}`,
          { method: "POST", body: input }
        )
      )
      if (
        data.case_id !== caseId ||
        data.transaction_id !== transactionId ||
        data.original.key !== transactionId ||
        data.proposed.currency !== currency ||
        data.original.currency !== currency ||
        data.proposed.amount_minor !== input.amount_minor ||
        data.proposed.direction !== input.direction ||
        Object.entries(input.fields ?? {}).some(
          ([key, value]) => data.field_changes?.[key] !== value
        ) ||
        (data.running_balances?.available &&
          data.running_balances.currency !== currency)
      )
        throw new Error(
          "The preview does not match this correction. Refresh the ledger."
        )
      return data
    },
  })
  const record = useMutation({
    retry: false,
    mutationFn: async ({
      reviewed,
      reason,
    }: {
      reviewed: CorrectionPreview
      reason: string
    }) => {
      const data = correctionAnswer.parse(
        await fetchAPI<unknown>(
          `/api/financial/transactions/${encodeURIComponent(reviewed.transaction_id)}/correction?${new URLSearchParams({ case_id: reviewed.case_id })}`,
          {
            method: "POST",
            body: {
              amount_minor: reviewed.proposed.amount_minor,
              direction: reviewed.proposed.direction,
              expected_revision: reviewed.document_revision,
              ...(reviewed.field_changes
                ? { fields: reviewed.field_changes }
                : {}),
              reason,
            },
          }
        )
      )
      if (
        data.case_id !== reviewed.case_id ||
        data.transaction_id !== reviewed.transaction_id ||
        data.replacement_id === data.transaction_id ||
        data.proof_class !== reviewed.verification.proposed_proof_class ||
        data.ledger_status !== reviewed.proposed.ledger_status
      )
        throw new Error("The response did not confirm the reviewed correction.")
      return data
    },
    onSuccess: () => {
      setCompletedDraft(savedDraft)
      clearDraft()
    },
    onSettled: (_data, _error, variables) => {
      void client.invalidateQueries({
        queryKey: ["ledger-source", variables.reviewed.case_id],
      })
      void client.invalidateQueries({
        queryKey: ["financial-linked-payments", variables.reviewed.case_id],
      })
      void client.invalidateQueries({
        queryKey: ["financial-ledger", variables.reviewed.case_id],
      })
      void client.invalidateQueries({
        queryKey: ["financial-decisions", variables.reviewed.case_id],
      })
      void client.invalidateQueries({
        queryKey: ["financial-proof-standing", variables.reviewed.case_id],
      })
    },
  })
  const busy = preview.isPending || record.isPending
  const finished = record.isSuccess || record.isError
  const reviewed = preview.data
  const refused =
    record.error instanceof ApiError &&
    [400, 401, 403, 404, 409, 422].includes(record.error.status)
  return (
    <section
      aria-label={initialRow ? "Correct transaction" : "Correct ledger amount"}
      className="space-y-3 rounded border p-4"
    >
      <h3 className="font-semibold">
        {initialRow ? "Correct transaction" : "Correct ledger amount"}
      </h3>
      <p className="text-sm">
        The original reading and citation stay in the ledger. A correction
        creates a replacement and records your reason.
      </p>
      {!finished && (
        <p className="text-sm text-muted-foreground">
          These edits are kept in this browser tab until you record the
          correction. After a refresh, open this transaction's correction again
          to continue. Closing the browser tab may discard unrecorded edits.
        </p>
      )}
      <label className="block text-sm">
        Proposed amount ({currency})
        <input
          className="ml-2 rounded border bg-background p-2"
          inputMode="decimal"
          maxLength={32}
          value={amount}
          disabled={busy || finished}
          onChange={(e) => {
            setDraft((current) => ({ ...current, amount: e.target.value }))
            preview.reset()
          }}
        />
      </label>
      <label className="block text-sm">
        Direction
        <select
          className="ml-2 rounded border bg-background p-2"
          value={direction}
          disabled={busy || finished}
          onChange={(e) => {
            setDraft((current) => ({
              ...current,
              direction: e.target.value as "credit" | "debit",
            }))
            preview.reset()
          }}
        >
          <option value="credit">Credit</option>
          <option value="debit">Debit</option>
        </select>
      </label>
      {initialRow && (
        <div className="grid gap-3 sm:grid-cols-2">
          {Object.entries(fieldLabels).map(([key, label]) => (
            <label className="block text-sm" key={key}>
              {label}
              <input
                className="block w-full rounded border bg-background p-2"
                type={key.endsWith("_date") ? "date" : "text"}
                value={editedFields[key]}
                maxLength={4000}
                disabled={busy || finished}
                onChange={(event) => {
                  setDraft((current) => ({
                    ...current,
                    editedFields: {
                      ...current.editedFields,
                      [key]: event.target.value,
                    },
                  }))
                  preview.reset()
                }}
              />
            </label>
          ))}
          <label className="block text-sm">
            Running balance ({currency})
            <input
              className="block w-full rounded border bg-background p-2"
              inputMode="decimal"
              value={balance}
              disabled={busy || finished}
              onChange={(event) => {
                setDraft((current) => ({
                  ...current,
                  balance: event.target.value,
                }))
                preview.reset()
              }}
            />
          </label>
          {balanceMinor === undefined && (
            <p role="alert">
              Enter the printed balance using a decimal point, or leave it empty
              if no balance is printed.
            </p>
          )}
        </div>
      )}
      {minor === null && amount && (
        <p role="alert">
          Enter an unsigned amount using a decimal point, with no separators and
          no more fractional digits than this currency permits.
        </p>
      )}
      {!finished && (
        <Button
          disabled={minor === null || balanceMinor === undefined || busy}
          onClick={() => {
            if (lock.current || minor === null) return
            lock.current = true
            preview.mutate(
              {
                amount_minor: minor,
                direction,
                ...(initialRow ? { fields: fieldChanges } : {}),
              },
              {
                onSettled: () => {
                  lock.current = false
                },
              }
            )
          }}
        >
          Preview correction
        </Button>
      )}
      {reviewed?.field_changes &&
        Object.keys(reviewed.field_changes).length > 0 && (
          <div className="rounded border p-3 text-sm">
            <h4 className="font-semibold">Changes to record</h4>
            {Object.entries(reviewed.field_changes).map(([key, value]) => (
              <p key={key}>
                {key === "running_balance_minor"
                  ? "Running balance"
                  : fieldLabels[key as keyof typeof fieldLabels] || key}
                :{" "}
                {value === null
                  ? "Not recorded"
                  : key === "running_balance_minor"
                    ? correctionMoney(value, currency)
                    : value}
              </p>
            ))}
          </div>
        )}
      {preview.isError && (
        <p role="alert">
          Preview unavailable: {preview.error.message}. Nothing was recorded.
        </p>
      )}
      {reviewed && !preview.isPending && (
        <div className="space-y-2 text-sm">
          <p>
            Original {reviewed.original.ref_id}:{" "}
            {correctionMoney(reviewed.original.amount_minor, currency)}{" "}
            {reviewed.original.direction}
          </p>
          <p>
            Proposed:{" "}
            {correctionMoney(reviewed.proposed.amount_minor, currency)}{" "}
            {reviewed.proposed.direction}
          </p>
          <p>Source document: {reviewed.original.source_document_id}</p>
          {reviewed.statement_identity && (
            <p>
              Statement difference:{" "}
              {reviewed.statement_identity.current.delta_minor === null
                ? "Unavailable"
                : correctionMoney(
                    reviewed.statement_identity.current.delta_minor,
                    currency
                  )}{" "}
              →{" "}
              {reviewed.statement_identity.proposed.delta_minor === null
                ? "Unavailable"
                : correctionMoney(
                    reviewed.statement_identity.proposed.delta_minor,
                    currency
                  )}{" "}
              ({reviewed.statement_identity.proposed.status}).
            </p>
          )}
          <p>{reviewed.limitation}</p>
          {reviewed.native_controls && (
            <NativeControlComparisonPanel
              comparison={reviewed.native_controls}
            />
          )}
          {reviewed.printed_totals && (
            <>
              <PrintedTotalChecks
                title="Printed totals before correction"
                checks={reviewed.printed_totals.current}
                currency={currency}
              />
              <PrintedTotalChecks
                title="Printed totals after proposed correction"
                checks={reviewed.printed_totals.proposed}
                currency={currency}
              />
            </>
          )}
          {reviewed.printed_totals_error && (
            <p role="alert">
              Printed totals could not be checked:{" "}
              {reviewed.printed_totals_error}
            </p>
          )}
          {reviewed.running_balances && (
            <RunningBalanceComparisonPanel
              caseId={caseId}
              comparison={reviewed.running_balances}
            />
          )}
          <p>
            Document verification: {reviewed.verification.current_proof_class} →{" "}
            {reviewed.verification.proposed_proof_class ?? "unavailable"}. This
            applies to all rows in this source document.
          </p>
          {reviewed.verification.can_record &&
            !reviewed.verification.included_in_default_totals && (
              <p className="font-semibold">
                This document will be excluded from default verified totals.
              </p>
            )}
          {reviewed.proposed.ledger_status === "quarantined" && (
            <p>The replacement remains quarantined and excluded from totals.</p>
          )}
          {reviewed.verification.reservations.map((reservation, i) => (
            <p key={i}>{reservation}</p>
          ))}
          {!reviewed.verification.can_record && (
            <p role="alert">{reviewed.verification.reason}</p>
          )}
        </div>
      )}
      <label className="block text-sm">
        Note about this correction (optional)
        <textarea
          aria-label="Reason for correction"
          className="mt-1 block w-full rounded border bg-background p-2"
          maxLength={4000}
          value={reason}
          disabled={busy || finished}
          onChange={(e) =>
            setDraft((current) => ({ ...current, reason: e.target.value }))
          }
        />
      </label>
      {record.isSuccess && (
        <p role="status">
          Correction recorded. Replacement citation:{" "}
          {record.data.replacement_ref_id}. Original citation:{" "}
          {reviewed?.original.ref_id}. Both readings remain available in the
          decision history.
        </p>
      )}
      {record.isError && (
        <p role="alert">
          {refused
            ? `Correction refused: ${record.error.message}. Close and review again.`
            : "The correction could not be confirmed. It may have been recorded. Check the refreshed ledger and decision history before trying again."}
        </p>
      )}
      <div className="flex gap-2">
        {!finished && (
          <Button
            disabled={
              busy ||
              !reviewed?.verification.can_record ||
              !reviewed.verification.proposed_proof_class
            }
            onClick={() => {
              if (lock.current || !reviewed?.verification.can_record) return
              lock.current = true
              record.mutate(
                { reviewed, reason },
                {
                  onSettled: () => {
                    lock.current = false
                  },
                }
              )
            }}
          >
            {record.isPending ? "Recording correction..." : "Record correction"}
          </Button>
        )}
        <Button variant="outline" disabled={busy} onClick={onClose}>
          Close correction
        </Button>
      </div>
    </section>
  )
}

export function CorrectionForm(
  props: Parameters<typeof CorrectionFormForm>[0]
) {
  const { canEdit } = useFinancialAccess()
  return canEdit ? <CorrectionFormForm {...props} /> : null
}
