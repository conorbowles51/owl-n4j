import { useFinancialAccess } from "../hooks/use-financial-access"
import { useState } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { z } from "zod"
import { Button } from "@/components/ui/button"
import { fetchAPI } from "@/lib/api-client"
import { caseworkKeys } from "@/features/workspace/hooks/use-casework"
import { useFinancialDraft } from "../stores/financial-drafts"
import { newReviewId } from "../lib/statement-review-id"
import { transactionDetail } from "../lib/transaction-detail"
import { formatLedgerAmount } from "../lib/ledger-format"
import {
  type PaymentDocumentProposal,
  savedPaymentDocument,
} from "../lib/payment-document"
import { TransactionSourceHighlight } from "./TransactionSourceHighlight"
import { LedgerSourceDialog } from "./LedgerSourceDialog"

const matchesSchema = z.object({
  case_id: z.string(),
  more_matches: z.boolean(),
  explanation: z.string(),
  candidates: z.array(
    z.object({
      transaction_id: z.string(),
      transaction: transactionDetail,
      filename: z.string(),
      revision: z.string(),
    })
  ),
})
const saveSchema = z.object({
  case_id: z.string(),
  entry_id: z.string(),
  created: z.boolean(),
  transaction_count: z.literal(0),
})
type Draft = {
  saved_entry_id?: string
  request_id: string
  title: string
  values: Record<string, string>
  reasons: Record<string, string>
  notes: string
  transaction_id: string | null
  transaction_revision: string | null
  link_reason: string
}

export function PaymentDocumentReview({
  data,
}: {
  data: PaymentDocumentProposal
}) {
  const { canEdit } = useFinancialAccess()
  const isReceipt = data.kind === "deposit_receipt"
  const amountKey = isReceipt ? "payment_amount" : "wire_amount"
  const dateKey = isReceipt ? "effective_date" : "value_date"
  const [initial] = useState<Draft>(() => ({
    request_id: newReviewId(),
    title:
      `${isReceipt ? "Receipt" : "Wire"} review: ${data.filename}${isReceipt ? ` · page ${data.page_numbers[0]}` : ""}`.slice(
        0,
        200
      ),
    values: Object.fromEntries(data.fields.map((f) => [f.key, f.value])),
    reasons: {},
    notes: "",
    transaction_id: null,
    transaction_revision: null,
    link_reason: "",
  }))
  const [draft, setDraft] = useFinancialDraft(
    data.case_id,
    `wire-review:${data.evidence_file_id}:${data.revision}`,
    initial
  )
  const [focus, setFocus] = useState<unknown>({
    kind: "page_only",
    page: data.page_numbers[0],
  })
  const [wholePage, setWholePage] = useState(true)
  const [selectedSource, setSelectedSource] = useState<string | null>(null)
  const client = useQueryClient()
  const endpoint = `/api/financial/statement-import/${data.evidence_file_id}/payment-document`
  const matches = useMutation({
    mutationFn: () =>
      fetchAPI(
        `${endpoint}/matches?case_id=${data.case_id}${data.document_id ? `&document_id=${data.document_id}` : ""}`,
        {
          method: "POST",
          body: {
            amount: draft.values[amountKey],
            currency: draft.values.currency,
            value_date: draft.values[dateKey],
          },
        }
      ).then((value) => matchesSchema.parse(value)),
  })
  const save = useMutation({
    mutationFn: () =>
      fetchAPI(`${endpoint}/save?case_id=${data.case_id}`, {
        method: "POST",
        body: {
          request_id: draft.request_id,
          ...(data.document_id ? { document_id: data.document_id } : {}),
          title: draft.title,
          values: draft.values,
          reasons: draft.reasons,
          notes: draft.notes,
          transaction_id: draft.transaction_id,
          transaction_revision: draft.transaction_revision,
          link_reason: draft.link_reason,
          expected_revision: data.revision,
        },
      }).then((value) => saveSchema.parse(value)),
    onSuccess: async (result) => {
      if (result.case_id === data.case_id) {
        setDraft((d) => ({ ...d, saved_entry_id: result.entry_id }))
        await Promise.all([
          client.invalidateQueries({
            queryKey: caseworkKeys.all(data.case_id),
          }),
          client.invalidateQueries({
            queryKey: ["statement-import-status", data.case_id],
          }),
        ])
      }
    },
  })
  const candidates =
    matches.data?.case_id === data.case_id
      ? matches.data.candidates.filter(
          (c) => c.transaction.case_id === data.case_id
        )
      : []
  const reasonsNeeded = data.fields.filter(
    (f) =>
      (draft.values[f.key] !== f.value ||
        (draft.values[f.key] && f.issues.length)) &&
      !draft.reasons[f.key]?.trim()
  )
  const canMatch =
    !!draft.values[amountKey] &&
    /^[A-Z]{3}$/.test(draft.values.currency || "") &&
    /^\d{4}-\d{2}-\d{2}$/.test(draft.values[dateKey] || "")
  const saved = !!draft.saved_entry_id || save.data?.case_id === data.case_id
  const edit = (key: string, value: string) => {
    setDraft((d) => ({
      ...d,
      values: { ...d.values, [key]: value },
      transaction_id: null,
      transaction_revision: null,
      link_reason: "",
    }))
    matches.reset()
  }
  return (
    <section
      className="space-y-4 py-4"
      aria-label={isReceipt ? "Deposit receipt review" : "Wire report review"}
    >
      <header>
        <h3 className="text-lg font-semibold">
          Review {isReceipt ? "deposit receipt" : "wire report"}:{" "}
          {data.filename}
        </h3>
        <p>
          Check the payment details against the original PDF, then save your
          observations in Findings. You can link the document to an existing
          payment. Saving this review adds no payment to account totals.
        </p>
      </header>
      {!data.supported ? (
        <div className="space-y-3">
          <p role="alert">{data.issues.join(" ")}</p>
          <label>
            Original PDF page{" "}
            <select
              aria-label={isReceipt ? "Receipt page" : "Wire report page"}
              className="rounded border bg-background p-2"
              onChange={(event) => {
                setFocus({
                  kind: "page_only",
                  page: Number(event.target.value),
                })
                setWholePage(true)
              }}
            >
              {data.page_numbers.map((page) => (
                <option key={page} value={page}>
                  {page}
                </option>
              ))}
            </select>
          </label>
          <div className="max-w-2xl">
            <TransactionSourceHighlight
              sourceDocumentId={data.evidence_file_id}
              locatorPayload={focus}
              wholePage={wholePage}
            />
          </div>
        </div>
      ) : (
        <>
          {isReceipt && data.issues.map((issue) => <p key={issue}>{issue}</p>)}
          <p className="text-sm text-muted-foreground">
            Unfinished changes are kept in this browser tab. Save the review to
            keep it with the case.
          </p>
          <div className="grid gap-4 xl:grid-cols-[minmax(300px,2fr)_minmax(0,3fr)] items-start">
            <div className="rounded border p-3 xl:sticky xl:top-2">
              <h4 className="font-semibold mb-2">
                Original {isReceipt ? "deposit receipt" : "wire report"}
              </h4>
              <TransactionSourceHighlight
                sourceDocumentId={data.evidence_file_id}
                locatorPayload={focus}
                wholePage={wholePage}
              />
            </div>
            <div className="space-y-4">
              {data.fields.map((field) => (
                <section
                  key={field.key}
                  className="rounded border p-3 space-y-2"
                >
                  <label className="block font-medium">
                    {field.label}
                    {field.input_type === "text" ? (
                      <textarea
                        aria-label={field.label}
                        className="block w-full min-h-16 rounded border bg-background p-2 font-normal"
                        maxLength={2000}
                        value={draft.values[field.key] || ""}
                        disabled={!canEdit || save.isPending || saved}
                        onChange={(e) => edit(field.key, e.target.value)}
                      />
                    ) : (
                      <input
                        aria-label={field.label}
                        className="block w-full rounded border bg-background p-2 font-normal"
                        type={field.input_type === "date" ? "date" : "text"}
                        maxLength={100}
                        placeholder={
                          field.input_type === "currency"
                            ? "e.g. USD"
                            : undefined
                        }
                        value={draft.values[field.key] || ""}
                        disabled={!canEdit || save.isPending || saved}
                        onChange={(e) =>
                          edit(
                            field.key,
                            field.input_type === "currency"
                              ? e.target.value.toUpperCase()
                              : e.target.value
                          )
                        }
                      />
                    )}
                  </label>
                  <p className="text-sm whitespace-pre-wrap">
                    <strong>Original reading:</strong> {field.raw || "Not read"}
                  </p>
                  {field.issues.map((issue, index) => (
                    <p
                      key={index}
                      className="text-sm text-amber-700 dark:text-amber-300"
                    >
                      {issue}
                    </p>
                  ))}
                  {field.source_cells.length > 0 && (
                    <div className="flex flex-wrap gap-2">
                      {field.source_cells.map((cell, index) => (
                        <Button
                          key={index}
                          size="sm"
                          variant="outline"
                          onClick={() => {
                            setFocus(cell.locator)
                            setWholePage(false)
                          }}
                        >
                          Show{" "}
                          {field.source_cells.length > 1
                            ? `line ${index + 1}`
                            : "value"}{" "}
                          in PDF
                        </Button>
                      ))}
                    </div>
                  )}
                  {(draft.values[field.key] !== field.value ||
                    field.issues.length > 0) && (
                    <label className="block text-sm">
                      Correction or check for {field.label.toLowerCase()}
                      <input
                        className="block w-full rounded border bg-background p-2"
                        maxLength={2000}
                        value={draft.reasons[field.key] || ""}
                        disabled={!canEdit || save.isPending || saved}
                        onChange={(e) =>
                          setDraft((d) => ({
                            ...d,
                            reasons: {
                              ...d.reasons,
                              [field.key]: e.target.value,
                            },
                          }))
                        }
                      />
                    </label>
                  )}
                </section>
              ))}
            </div>
          </div>
          <section
            className="rounded border p-4 space-y-3"
            aria-label={
              isReceipt
                ? "Link a receipt to an imported payment"
                : "Link a wire to an imported payment"
            }
          >
            <h4 className="font-semibold">
              Link to a payment already in this case
            </h4>
            <p>
              Look for the same currency and amount within three days of the
              {isReceipt
                ? "effective date. Only incoming payments are offered."
                : "value date."}{" "}
              Open both sources before choosing a payment. You can save this
              review without a link.
            </p>
            <Button
              variant="outline"
              disabled={
                !canMatch || matches.isPending || save.isPending || saved
              }
              onClick={() => {
                setDraft((d) => ({
                  ...d,
                  transaction_id: null,
                  transaction_revision: null,
                  link_reason: "",
                }))
                matches.mutate()
              }}
            >
              {matches.isPending
                ? "Finding payments…"
                : "Find matching payments"}
            </Button>
            {matches.isError && <p role="alert">{matches.error.message}</p>}
            {matches.isSuccess && !candidates.length && (
              <p>
                No imported payments match these details. This review can still
                be saved.
              </p>
            )}
            {matches.data?.more_matches && (
              <p>
                More than 25 payments match. The first 25 are shown. Check the
                account and original source carefully.
              </p>
            )}
            {candidates.map((candidate) => (
              <div
                className="flex flex-wrap gap-2 items-center rounded border p-3"
                key={candidate.transaction_id}
              >
                <label className="flex gap-2 items-start">
                  <input
                    type="radio"
                    name="wire-payment"
                    disabled={!canEdit || saved || save.isPending}
                    checked={draft.transaction_id === candidate.transaction_id}
                    onChange={() =>
                      setDraft((d) => ({
                        ...d,
                        transaction_id: candidate.transaction_id,
                        transaction_revision: candidate.revision,
                      }))
                    }
                  />
                  <span>
                    {candidate.transaction.ordering_date} ·{" "}
                    {candidate.transaction.description || "Payment"} ·{" "}
                    {
                      formatLedgerAmount(
                        candidate.transaction.amount_minor,
                        candidate.transaction.currency
                      ).text
                    }{" "}
                    {candidate.transaction.currency}
                    <br />
                    {candidate.transaction.account_label || candidate.filename}
                  </span>
                </label>
                <Button
                  variant="outline"
                  onClick={() => setSelectedSource(candidate.transaction_id)}
                >
                  Open payment and source
                </Button>
              </div>
            ))}
            {draft.transaction_id && (
              <>
                <Button
                  variant="outline"
                  onClick={() => setSelectedSource(draft.transaction_id)}
                >
                  Open selected payment and source
                </Button>
                <label className="block">
                  Why does this document support the selected payment?
                  <textarea
                    className="block w-full rounded border bg-background p-2"
                    maxLength={2000}
                    value={draft.link_reason}
                    disabled={!canEdit || save.isPending || saved}
                    onChange={(e) =>
                      setDraft((d) => ({ ...d, link_reason: e.target.value }))
                    }
                  />
                </label>
                <Button
                  variant="ghost"
                  disabled={!canEdit || save.isPending || saved}
                  onClick={() =>
                    setDraft((d) => ({
                      ...d,
                      transaction_id: null,
                      transaction_revision: null,
                      link_reason: "",
                    }))
                  }
                >
                  Remove payment link
                </Button>
              </>
            )}
          </section>
          <section className="rounded border p-4 space-y-3">
            <label className="block">
              Review title
              <input
                className="block w-full rounded border bg-background p-2"
                value={draft.title}
                maxLength={200}
                disabled={!canEdit || save.isPending || saved}
                onChange={(e) =>
                  setDraft((d) => ({ ...d, title: e.target.value }))
                }
              />
            </label>
            <label className="block">
              Your observations
              <textarea
                className="block w-full min-h-24 rounded border bg-background p-2"
                value={draft.notes}
                maxLength={8000}
                disabled={!canEdit || save.isPending || saved}
                onChange={(e) =>
                  setDraft((d) => ({ ...d, notes: e.target.value }))
                }
              />
            </label>
            {reasonsNeeded.length > 0 && (
              <p>
                Explain the corrections or checks above for:{" "}
                {reasonsNeeded.map((f) => f.label.toLowerCase()).join(", ")}.
              </p>
            )}
            <Button
              disabled={
                !canEdit ||
                !data.supported ||
                !canMatch ||
                !draft.title.trim() ||
                !!reasonsNeeded.length ||
                (!!draft.transaction_id && !draft.link_reason.trim()) ||
                save.isPending ||
                saved
              }
              onClick={() => {
                if (!canEdit) return
                setDraft(draft)
                save.mutate()
              }}
            >
              {save.isPending
                ? "Saving review…"
                : isReceipt
                  ? "Save receipt review"
                  : "Save wire review"}
            </Button>
            {save.isError && (
              <p role="alert">
                {save.error.message} Your review is still here.
              </p>
            )}
            {saved && (
              <div className="space-y-2">
                <p role="status">
                  {isReceipt ? "Receipt" : "Wire"} review saved in Findings. No
                  payment was added.{" "}
                  <a
                    className="underline"
                    href={`/cases/${data.case_id}/financial?view=findings`}
                  >
                    Open Findings
                  </a>
                </p>
                <Button
                  variant="outline"
                  onClick={() => {
                    setDraft((d) => ({
                      ...d,
                      request_id: newReviewId(),
                      saved_entry_id: undefined,
                    }))
                    save.reset()
                  }}
                >
                  Create another review
                </Button>
                <p className="text-sm">
                  Create another review if you need to record a later
                  correction. The earlier saved review stays in Findings.
                </p>
              </div>
            )}
          </section>
        </>
      )}
      {selectedSource && (
        <LedgerSourceDialog
          caseId={data.case_id}
          transactionId={selectedSource}
          onClose={() => setSelectedSource(null)}
        />
      )}
    </section>
  )
}

export function SavedPaymentDocument({
  metadata,
  caseId,
  fileId,
}: {
  metadata: unknown
  caseId: string
  fileId: string
}) {
  const parsed = savedPaymentDocument.safeParse(metadata)
  const [focus, setFocus] = useState<unknown | null>(null)
  const [wholePage, setWholePage] = useState(true)
  if (
    !parsed.success ||
    parsed.data.original.case_id !== caseId ||
    parsed.data.original.evidence_file_id !== fileId
  )
    return (
      <p role="alert">
        The saved document details do not match this case and document.
      </p>
    )
  const saved = parsed.data
  return (
    <section
      className="space-y-3"
      aria-label={
        saved.original.kind === "deposit_receipt"
          ? "Saved receipt details"
          : "Saved wire details"
      }
    >
      <details>
        <summary className="cursor-pointer">
          Compare the saved values with their original readings
        </summary>
        <dl className="space-y-3 mt-2">
          {saved.original.fields.map((field) => (
            <div key={field.key} className="rounded border p-3">
              <dt className="font-semibold">{field.label}</dt>
              <dd className="whitespace-pre-wrap">
                Saved: {saved.reviewed_values[field.key] || "Not recorded"}
              </dd>
              <dd className="text-sm whitespace-pre-wrap">
                Original reading: {field.raw || "Not read"}
              </dd>
              {saved.correction_reasons[field.key] && (
                <dd className="text-sm">
                  Correction or check: {saved.correction_reasons[field.key]}
                </dd>
              )}
              {field.source_cells.map((cell, index) => (
                <Button
                  key={index}
                  size="sm"
                  variant="outline"
                  onClick={() => {
                    setFocus(cell.locator)
                    setWholePage(false)
                  }}
                >
                  Show{" "}
                  {field.source_cells.length > 1
                    ? `line ${index + 1}`
                    : "value"}{" "}
                  in original PDF
                </Button>
              ))}
            </div>
          ))}
        </dl>
      </details>
      <Button
        variant="outline"
        onClick={() => {
          setFocus({ kind: "page_only", page: saved.original.page_numbers[0] })
          setWholePage(true)
        }}
      >
        Open original{" "}
        {saved.original.kind === "deposit_receipt"
          ? "deposit receipt"
          : "wire report"}
      </Button>
      {focus !== null && (
        <div className="max-w-2xl rounded border p-3">
          <Button variant="ghost" onClick={() => setFocus(null)}>
            Close original report
          </Button>
          <TransactionSourceHighlight
            sourceDocumentId={fileId}
            locatorPayload={focus}
            wholePage={wholePage}
          />
        </div>
      )}
    </section>
  )
}
