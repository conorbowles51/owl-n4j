import { useRef, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { fetchAPI } from "@/lib/api-client"
import { Button } from "@/components/ui/button"
import { correctionMinor, correctionMoney } from "../lib/correction-contract"
import {
  assertCandidateScope,
  candidateAccounts,
  candidateAssessment,
  candidateReview,
  candidateUrl,
  fetchCandidateReview,
  type CandidateReading,
  type CandidateReview,
} from "../lib/candidate-contract"
import {
  CandidateAccountForm,
  type CandidateAccount,
} from "./CandidateAccountForm"
import { TransactionSourceHighlight } from "./TransactionSourceHighlight"

const fieldClass = "block w-full rounded border bg-background p-2 text-sm"

export function CandidateReviewForm({
  caseId,
  candidateId,
  mappingId,
  fileId,
  onClose,
}: {
  caseId: string
  candidateId: string
  mappingId: string
  fileId: string
  onClose: () => void
}) {
  const [reload, setReload] = useState(0)
  const query = useQuery({
    queryKey: ["financial-candidates", caseId, "review", candidateId, reload],
    queryFn: () => fetchCandidateReview(caseId, candidateId),
    retry: false,
    refetchOnWindowFocus: false,
  })
  return (
    <section
      aria-label="Review PDF reading"
      className="space-y-3 rounded border p-4"
    >
      <div className="flex items-center justify-between">
        <h3 className="font-semibold">Review PDF reading</h3>
        <Button variant="ghost" onClick={onClose}>
          Close review
        </Button>
      </div>
      {query.isError ? (
        <p role="alert">Review could not be loaded. {query.error.message}</p>
      ) : query.isPending ? (
        <p role="status">Loading review…</p>
      ) : (
        <ReviewFields
          key={`${candidateId}:${query.data.review_revision}:${query.data.finalization_id}:${reload}`}
          review={query.data}
          caseId={caseId}
          mappingId={mappingId}
          fileId={fileId}
          onReload={() => setReload((n) => n + 1)}
        />
      )}
      {query.isError && (
        <Button onClick={() => setReload((n) => n + 1)}>Reload review</Button>
      )}
    </section>
  )
}

function ReviewFields({
  review,
  caseId,
  mappingId,
  fileId,
  onReload,
}: {
  review: CandidateReview
  caseId: string
  mappingId: string
  fileId: string
  onReload: () => void
}) {
  const finalized = review.finalization_id !== null
  const previous = review.reading
  const [currency, setCurrency] = useState(previous?.currency ?? "")
  const [sourceCurrency, setSourceCurrency] = useState(previous?.currency ?? "")
  const assessmentCurrency = finalized ? sourceCurrency : currency
  const [amount, setAmount] = useState(
    previous
      ? correctionMoney(previous.amount_minor, previous.currency).slice(
          0,
          -previous.currency.length - 1
        )
      : ""
  )
  const [account, setAccount] = useState(previous?.account_id ?? "")
  const [newAccount, setNewAccount] = useState<CandidateAccount | null>(null)
  const [accountBusy, setAccountBusy] = useState(false)
  const accountBusyRef = useRef(false)
  const [direction, setDirection] = useState(previous?.direction ?? "")
  const [bookingDate, setBookingDate] = useState(previous?.booking_date ?? "")
  const [valueDate, setValueDate] = useState(previous?.value_date ?? "")
  const [transactionDate, setTransactionDate] = useState(
    previous?.transaction_date ?? ""
  )
  const [description, setDescription] = useState(previous?.description ?? "")
  const [reason, setReason] = useState("")
  const [search, setSearch] = useState("")
  const [blocked, setBlocked] = useState(false)
  const lock = useRef(false)
  const client = useQueryClient()
  const accounts = useQuery({
    queryKey: ["financial-candidates", caseId, "accounts", search],
    retry: false,
    queryFn: async () => {
      const data = candidateAccounts.parse(
        await fetchAPI<unknown>(
          `${candidateUrl("ledger-accounts", caseId)}&${new URLSearchParams({ search })}`
        )
      )
      assertCandidateScope(data, caseId)
      return data
    },
  })
  const assessment = useMutation({
    retry: false,
    mutationFn: async (requestedCurrency: string) => {
      const data = candidateAssessment.parse(
        await fetchAPI<unknown>(
          candidateUrl(
            `candidates/${review.candidate_id}/amount-assessment`,
            caseId
          ),
          { method: "POST", body: { currency: requestedCurrency } }
        )
      )
      assertCandidateScope(data, caseId)
      if (
        data.candidate_id !== review.candidate_id ||
        data.mapping_id !== mappingId ||
        data.currency !== requestedCurrency ||
        data.review_revision !== review.review_revision
      )
        throw new Error("This reading changed. Reload the review.")
      return data
    },
  })
  const record = useMutation({
    retry: false,
    mutationFn: async (input: {
      status: "pending" | "resolved" | "rejected"
      reading: CandidateReading | null
    }) => {
      const data = candidateReview.parse(
        await fetchAPI<unknown>(
          candidateUrl(`candidates/${review.candidate_id}/review`, caseId),
          {
            method: "POST",
            body: {
              ...input,
              reason,
              expected_revision: review.review_revision,
            },
          }
        )
      )
      assertCandidateScope(data, caseId)
      if (
        data.candidate_id !== review.candidate_id ||
        data.status !== input.status ||
        data.review_revision === review.review_revision ||
        JSON.stringify(data.reading) !== JSON.stringify(input.reading)
      )
        throw new Error(
          "The saved response does not match this review. Reload to check its outcome."
        )
      return data
    },
    onSettled: () => {
      setBlocked(true)
      void client.invalidateQueries({
        queryKey: ["financial-candidates", caseId, "mapping"],
      })
    },
  })
  const minor = correctionMinor(amount, currency)
  const accountOptions = (
    newAccount
      ? [
          newAccount,
          ...(accounts.data?.items ?? []).filter(
            (item) => item.id !== newAccount.id
          ),
        ]
      : (accounts.data?.items ?? [])
  ).filter((item) => !item.source_file_id || item.source_file_id === fileId)
  const selectedAccount = accountOptions.find((item) => item.id === account)
  const ready = Boolean(
    minor !== null &&
    account &&
    selectedAccount &&
    (!selectedAccount.currency || selectedAccount.currency === currency) &&
    direction &&
    [bookingDate, valueDate, transactionDate].some(Boolean) &&
    [bookingDate, valueDate, transactionDate].every(
      (value) => !value || /^\d{4}-\d{2}-\d{2}$/.test(value)
    )
  )
  const send = (status: "pending" | "resolved" | "rejected") => {
    if (
      finalized ||
      lock.current ||
      accountBusyRef.current ||
      blocked ||
      !reason.trim() ||
      (status === "resolved" && !ready)
    )
      return
    lock.current = true
    const reading: CandidateReading | null =
      status === "resolved"
        ? {
            account_id: account,
            currency,
            amount_minor: minor!,
            direction: direction as "credit" | "debit",
            booking_date: bookingDate || null,
            value_date: valueDate || null,
            transaction_date: transactionDate || null,
            description,
          }
        : null
    record.mutate({ status, reading })
  }
  const disabled = record.isPending || blocked || accountBusy
  return (
    <div className="space-y-3 text-sm">
      <p>
        Review status: <strong>{review.status}</strong>.
      </p>
      {finalized ? (
        <p role="status">
          Finalized reading. Original values and review history are read-only.
          {review.status === "resolved"
            ? " This reading was added to the ledger. Use ledger corrections for later changes."
            : " This rejected reading was retained in the finalized batch and was not added to the ledger."}{" "}
          Finalization alone does not include readings in verified totals.
        </p>
      ) : (
        <p>
          These readings are outside ledger totals, including after resolution.
        </p>
      )}
      <ul className="space-y-1">
        {review.original.cells.map((cell) => (
          <li key={cell.column_index}>
            <strong>{cell.proposed_meaning.replaceAll("_", " ")}:</strong>{" "}
            <span className="whitespace-pre-wrap">
              {cell.text ?? cell.source?.text}
            </span>
          </li>
        ))}
      </ul>
      <fieldset
        disabled={disabled || finalized}
        className="grid gap-3 sm:grid-cols-2"
      >
        <label>
          Currency
          <input
            className={fieldClass}
            value={currency}
            maxLength={3}
            onChange={(e) => {
              setCurrency(e.target.value.toUpperCase())
              assessment.reset()
            }}
            placeholder="GBP"
          />
        </label>
        <label>
          Reviewed amount
          <input
            className={fieldClass}
            inputMode="decimal"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            placeholder="12.34"
          />
        </label>
        <label>
          Search accounts
          <input
            className={fieldClass}
            value={search}
            maxLength={128}
            onChange={(e) => setSearch(e.target.value)}
          />
        </label>
        <label>
          Account
          <select
            aria-label="Account"
            className={fieldClass}
            value={account}
            onChange={(e) => setAccount(e.target.value)}
          >
            <option value="">Choose an account</option>
            {accountOptions.map((item) => (
              <option key={item.id} value={item.id}>
                {[
                  item.display_label,
                  item.provisional ? "Provisional" : null,
                  item.holder,
                  item.institution,
                  item.identifier,
                  item.currency,
                ]
                  .filter(Boolean)
                  .join(" · ") || `Account ${item.id}`}
              </option>
            ))}
          </select>
        </label>
        <label>
          Direction
          <select
            aria-label="Direction"
            className={fieldClass}
            value={direction}
            onChange={(e) => setDirection(e.target.value)}
          >
            <option value="">Choose a direction</option>
            <option value="debit">Money out</option>
            <option value="credit">Money in</option>
          </select>
        </label>
        <label>
          Booking date
          <input
            className={fieldClass}
            type="date"
            value={bookingDate}
            onChange={(e) => setBookingDate(e.target.value)}
          />
        </label>
        <label>
          Value date
          <input
            className={fieldClass}
            type="date"
            value={valueDate}
            onChange={(e) => setValueDate(e.target.value)}
          />
        </label>
        <label>
          Transaction date
          <input
            className={fieldClass}
            type="date"
            value={transactionDate}
            onChange={(e) => setTransactionDate(e.target.value)}
          />
        </label>
        <label>
          Description
          <input
            className={fieldClass}
            value={description}
            maxLength={4096}
            onChange={(e) => setDescription(e.target.value)}
          />
        </label>
        <label className="sm:col-span-2">
          Reason for decision
          <textarea
            aria-label="Reason for decision"
            className={fieldClass}
            value={reason}
            maxLength={4096}
            onChange={(e) => setReason(e.target.value)}
          />
        </label>
      </fieldset>
      {!finalized && (
        <CandidateAccountForm
          caseId={caseId}
          candidateId={review.candidate_id}
          fileId={fileId}
          reviewRevision={review.review_revision}
          currency={currency}
          disabled={record.isPending || blocked}
          onBusy={(busy) => {
            accountBusyRef.current = busy
            setAccountBusy(busy)
          }}
          onCreated={(created) => {
            setNewAccount(created)
            setAccount(created.id)
          }}
        />
      )}
      {accounts.isError && (
        <p role="alert">
          Accounts could not be loaded. {accounts.error.message}
        </p>
      )}
      {accounts.data?.has_more && (
        <p>More accounts are available. Narrow the account search.</p>
      )}
      {accounts.data?.items.length === 0 && (
        <p>
          No matching ledger accounts. An account must exist before this reading
          can be resolved.
        </p>
      )}
      {finalized && (
        <label>
          Currency for source assessment
          <input
            className={fieldClass}
            value={sourceCurrency}
            maxLength={3}
            onChange={(e) => {
              setSourceCurrency(e.target.value.toUpperCase())
              assessment.reset()
            }}
          />
        </label>
      )}
      <Button
        variant="outline"
        disabled={
          disabled ||
          assessment.isPending ||
          !/^[A-Z]{3}$/.test(assessmentCurrency)
        }
        onClick={() => assessment.mutate(assessmentCurrency)}
      >
        Assess original amounts
      </Button>
      {assessment.isError && (
        <p role="alert">Assessment failed. {assessment.error.message}</p>
      )}
      {assessment.data && assessment.data.currency === assessmentCurrency && (
        <div className="space-y-3">
          <p>
            Currency supplied for assessment: {assessmentCurrency}. Column
            meanings remain proposals.
          </p>
          {assessment.data.amount_cells.map((cell) => (
            <div
              key={cell.column_index}
              className="space-y-2 rounded border p-3"
            >
              <p>
                Original {cell.proposed_meaning}: {cell.source.text}
              </p>
              <p>{cell.error ?? cell.assessment?.explanation}</p>
              {cell.assessment?.minor_units !== undefined && (
                <p>
                  Numeric reading:{" "}
                  {correctionMoney(
                    cell.assessment.minor_units,
                    assessmentCurrency
                  )}
                </p>
              )}
              {cell.assessment?.proposals?.map((p, index) => (
                <p key={index}>
                  Possible reading:{" "}
                  {correctionMoney(p.minor_units, assessmentCurrency)}.{" "}
                  {p.basis}
                </p>
              ))}
              <TransactionSourceHighlight
                sourceDocumentId={fileId}
                locatorPayload={
                  cell.source.locator ??
                  (cell.source.page_number
                    ? { kind: "page_only", page: cell.source.page_number }
                    : { kind: "unlocated" })
                }
                valueLabel={cell.source.text}
              />
            </div>
          ))}
          {assessment.data.unclassified_columns.length > 0 && (
            <p>
              Some columns have no identified meaning and were not assessed as
              amounts.
            </p>
          )}
        </div>
      )}
      <div className="flex flex-wrap gap-2">
        {!finalized && (
          <>
            <Button
              disabled={disabled || !reason.trim() || !ready}
              onClick={() => send("resolved")}
            >
              Record resolved reading
            </Button>
            <Button
              variant="outline"
              disabled={
                disabled || !reason.trim() || review.status === "rejected"
              }
              onClick={() => send("rejected")}
            >
              Reject reading
            </Button>
            <Button
              variant="outline"
              disabled={
                disabled || !reason.trim() || review.status === "pending"
              }
              onClick={() => send("pending")}
            >
              Reopen for review
            </Button>
          </>
        )}
        <Button variant="ghost" disabled={record.isPending} onClick={onReload}>
          Reload review
        </Button>
      </div>
      {record.isPending && <p role="status">Recording review…</p>}
      {record.isSuccess && (
        <p role="status">
          Review recorded. Reload to see its current state and history.
        </p>
      )}
      {record.isError && (
        <p role="alert">
          The review was not confirmed. Reload to check its outcome before
          trying again. {record.error.message}
        </p>
      )}
      <details>
        <summary>Review history ({review.history.length})</summary>
        {review.history.map((event) => (
          <div key={event.id} className="my-2 rounded border p-2">
            <p>
              {event.status} · {event.actor.name} ·{" "}
              {new Date(event.created_at).toLocaleString()}
            </p>
            <p>{event.reason}</p>
            {event.reading && (
              <p>
                {correctionMoney(
                  event.reading.amount_minor,
                  event.reading.currency
                )}{" "}
                · {event.reading.direction} ·{" "}
                {event.reading.booking_date ??
                  event.reading.value_date ??
                  event.reading.transaction_date}
              </p>
            )}
          </div>
        ))}
      </details>
    </div>
  )
}
