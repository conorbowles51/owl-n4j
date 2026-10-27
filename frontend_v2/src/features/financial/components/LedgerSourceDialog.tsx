import { PaymentLabelsEditor } from "./PaymentLabelsEditor"
import { PaymentLabelOrigin } from "./PaymentLabelOrigin"
import { Disclosure } from "./Disclosure"
import { InfoTip } from "./InfoTip"
import { RowJudgementMarkers } from "./JudgementCalls"
import { useRowJudgementLookup } from "../hooks/use-judgement-rows"
import { categoryTone } from "../lib/category-palette"
import {
  absentPaymentBalance,
  paymentBalanceExplanation,
} from "../lib/payment-balance"
import { NearbyPaymentSearch } from "./NearbyPaymentSearch"
import { InvestigatorFindingEditor } from "./InvestigatorFindingEditor"
import { useFinancialFindingIndex } from "../hooks/use-financial-finding-index"
import { useFinancialAccess } from "../hooks/use-financial-access"
import type { LedgerTransaction } from "../api"
import { citationSchema } from "../lib/source-citation"
import {
  formatLedgerAmount,
  readExtractionLayer,
  readLedgerStatus,
  readProofClass,
} from "../lib/ledger-format"
import { CorrectionForm } from "./CorrectionForm"
import { TransactionNote } from "./TransactionNote"
import { SourceCustodyPanel } from "./SourceCustodyPanel"
import { useState, type ReactNode } from "react"
import { useQuery } from "@tanstack/react-query"
import { fetchAPI } from "@/lib/api-client"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog"
import { DocumentViewer } from "@/components/ui/document-viewer"
import { Button } from "@/components/ui/button"
import { evidenceAPI } from "@/features/evidence/api"
import { readLocator } from "../lib/locator"
import { TransactionSourceHighlight } from "./TransactionSourceHighlight"
import { SourceAmountPanel } from "./SourceAmountPanel"

export function LedgerSourceDialog({
  caseId,
  transactionId,
  onClose,
  initialNoteOpen = false,
  onAdjudicate,
  inline = false,
  allowNearby = true,
}: {
  caseId: string
  transactionId: string
  onClose: () => void
  inline?: boolean
  allowNearby?: boolean
  initialNoteOpen?: boolean
  onAdjudicate?: (row: LedgerTransaction) => void
}) {
  const { canEdit } = useFinancialAccess()
  const findingIndex = useFinancialFindingIndex(caseId)
  const linkedFindings =
    findingIndex.data?.filter((entry) =>
      entry.payment_ids.includes(transactionId)
    ) ?? []
  const [replacement, setReplacement] = useState<string | null>(null)
  const [viewFile, setViewFile] = useState(false)
  const [assessAmount, setAssessAmount] = useState(false)
  const [editingLabels, setEditingLabels] = useState(false)
  const [correcting, setCorrecting] = useState(false)
  const [finding, setFinding] = useState(false)
  const source = useQuery({
    queryKey: ["ledger-source", caseId, transactionId],
    retry: false,
    queryFn: async ({ signal }) => {
      const data = citationSchema.parse(
        await fetchAPI(
          `/api/financial/ledger/${encodeURIComponent(transactionId)}/source?${new URLSearchParams({ case_id: caseId })}`,
          { signal }
        )
      )
      if (
        data.case_id !== caseId ||
        data.transaction_id !== transactionId ||
        (data.transaction &&
          (data.transaction.key !== transactionId ||
            data.transaction.case_id !== caseId ||
            data.transaction.source_document_id !== data.source_document_id)) ||
        (data.locator_state === "stored"
          ? !readLocator(data.locator).ok
          : data.locator !== null)
      )
        throw new Error(
          "Source citation is inconsistent. Reload the ledger before opening it."
        )
      return data
    },
  })
  const data = source.data
  const location = data ? readLocator(data.locator) : null
  const page =
    location?.ok && "page" in location.locator
      ? (location.locator.page ?? undefined)
      : undefined
  if (replacement)
    return (
      <LedgerSourceDialog
        inline={inline}
        allowNearby={allowNearby}
        key={replacement}
        caseId={caseId}
        transactionId={replacement}
        onClose={onClose}
        onAdjudicate={onAdjudicate}
      />
    )
  return (
    <>
      <SourceFrame
        inline={inline}
        open={(!viewFile || source.isError) && !finding}
        onClose={onClose}
      >
        {inline ? (
          <header className="flex justify-between items-center gap-2">
            <h2 className="flex items-center gap-1.5 font-semibold">
              Transaction details
              <InfoTip text="This payment stays open after a refresh, until you close it." />
            </h2>
            <Button variant="ghost" size="sm" onClick={onClose}>
              Close details
            </Button>
          </header>
        ) : (
          <DialogHeader>
            <DialogTitle>Transaction details</DialogTitle>
            <DialogDescription>
              {canEdit
                ? "Check the payment against its statement, record a note, or correct a value."
                : "Check the payment against its original statement."}
            </DialogDescription>
          </DialogHeader>
        )}
        {source.isPending && <p role="status">Loading transaction details…</p>}
        {source.isError && (
          <div role="alert" className="space-y-2">
            <p>
              Transaction details could not be loaded. {source.error.message}
            </p>
            <Button
              variant="outline"
              disabled={source.isFetching}
              onClick={() => void source.refetch()}
            >
              {source.isFetching
                ? "Retrying transaction…"
                : "Try loading this transaction again"}
            </Button>
          </div>
        )}
        {data && !source.isError && (
          <>
            {findingIndex.isError && (
              <p role="alert" className="text-sm">
                Saved finding links could not be loaded.{" "}
                <button
                  className="underline"
                  onClick={() => void findingIndex.refetch()}
                >
                  Reload finding links
                </button>
              </p>
            )}
            {!!linkedFindings.length && (
              <section className="rounded-md border border-[#c9d8f5] bg-[#e6efff] p-3 space-y-2">
                <h3 className="font-semibold text-[#1f4fa8]">
                  Findings linked to this payment ({linkedFindings.length})
                </h3>
                {linkedFindings.map((entry) => (
                  <a
                    key={entry.id}
                    className="block text-sm underline"
                    href={`/cases/${caseId}/workspace?view=casework&entry=${entry.id}`}
                  >
                    {entry.title || "Untitled finding"}
                  </a>
                ))}
              </section>
            )}
            {data.transaction && (
              <section className="space-y-4" aria-label="Payment details">
                <PaymentHeader
                  transaction={data.transaction}
                  ledgerStatus={data.ledger_status}
                />
                <AccountOwnershipReview
                  caseId={caseId}
                  accountIds={[data.transaction.account_id]}
                  label="Review this account’s ownership"
                />
                {data.transaction.ordering_date_context ===
                  "statement_end_ordering_only" && (
                  <p className="text-sm">
                    Statement ends {data.transaction.ordering_date}. This date
                    is used to place the charge in order; no transaction date
                    was printed.
                  </p>
                )}
                <PaymentJudgements
                  caseId={caseId}
                  transaction={data.transaction}
                />
                <DrawerSection title="Who">
                  <dl className="grid grid-cols-2 gap-3 text-sm">
                    <div>
                      <dt className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                        From
                      </dt>
                      <dd>
                        {data.transaction.from_name || "Not identified"}
                        <PaymentLabelOrigin
                          row={data.transaction}
                          field="from_name"
                          detail
                        />
                      </dd>
                    </div>
                    <div>
                      <dt className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                        To
                      </dt>
                      <dd>
                        {data.transaction.to_name || "Not identified"}
                        <PaymentLabelOrigin
                          row={data.transaction}
                          field="to_name"
                          detail
                        />
                      </dd>
                    </div>
                  </dl>
                </DrawerSection>
                <DrawerSection title="Category">
                  <dl className="text-sm">
                    <dt className="sr-only">Category</dt>
                    <dd>
                      <span
                        className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 font-semibold ${data.transaction.category ? "" : "border-dashed"}`}
                        style={
                          data.transaction.category
                            ? {
                                background: categoryTone(
                                  data.transaction.category
                                ).tint,
                                color: categoryTone(data.transaction.category)
                                  .text,
                              }
                            : undefined
                        }
                      >
                        {data.transaction.category && (
                          <span
                            aria-hidden="true"
                            className="h-2.5 w-2.5 rounded-full"
                            style={{
                              background: categoryTone(
                                data.transaction.category
                              ).dot,
                            }}
                          />
                        )}
                        {data.transaction.category || "Uncategorized"}
                      </span>
                      <PaymentLabelOrigin
                        row={data.transaction}
                        field="category"
                        detail
                      />
                    </dd>
                  </dl>
                </DrawerSection>
                <DrawerSection title="Source">
                  <dl className="grid grid-cols-2 gap-3 text-sm">
                    <div className="col-span-2">
                      <dt className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                        As printed on the statement
                      </dt>
                      <dd className="font-mono text-[13px] break-words">
                        {data.transaction.description ||
                          "No description recorded"}
                      </dd>
                    </div>
                    <div>
                      <dt className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                        Printed balance
                      </dt>
                      <dd>
                        {data.transaction.running_balance_minor != null
                          ? `${formatLedgerAmount(data.transaction.running_balance_minor, data.transaction.currency).text} ${data.transaction.currency}`
                          : absentPaymentBalance(data.transaction)}
                      </dd>
                      {data.transaction.running_balance_minor == null && (
                        <p className="text-xs text-muted-foreground">
                          {paymentBalanceExplanation(data.transaction)}
                        </p>
                      )}
                    </div>
                    <div>
                      <dt className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                        Bank reference
                      </dt>
                      <dd>
                        {data.transaction.bank_reference || "Not recorded"}
                      </dd>
                    </div>
                    {page !== undefined && (
                      <div>
                        <dt className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                          Page
                        </dt>
                        <dd>Page {page}</dd>
                      </div>
                    )}
                  </dl>
                  <p className="font-medium">
                    {data.ref_id} · {data.filename}
                  </p>
                  {data.ledger_status === "superseded" && (
                    <div className="space-y-2 rounded-md border border-[#e9b949] bg-[#fdf0d5] p-3 text-[#8a5300]">
                      <p>This is the original transaction before correction.</p>
                      {data.superseded_by_id && (
                        <Button
                          variant="outline"
                          onClick={() => setReplacement(data.superseded_by_id)}
                        >
                          Open corrected transaction
                        </Button>
                      )}
                    </div>
                  )}
                  {data.locator_state === "missing" && (
                    <p>
                      No location was stored for this row. You can open the
                      source file.
                    </p>
                  )}
                  {data.locator_state === "invalid" && (
                    <p>
                      The stored location could not be read. You can open the
                      source file without a highlight.
                    </p>
                  )}
                  {data.locator_state === "stored" && (
                    <TransactionSourceHighlight
                      locatorPayload={data.locator}
                      sourceDocumentId={
                        data.filename.toLowerCase().endsWith(".pdf")
                          ? data.evidence_file_id
                          : undefined
                      }
                      valueLabel={data.ref_id}
                    />
                  )}
                  <Button onClick={() => setViewFile(true)}>
                    Open source file
                  </Button>
                  {data.transaction.transfer_details && (
                    <Disclosure label="Sender, recipient and account details printed in this transfer">
                      <div className="mt-2 rounded-md border p-3 text-sm">
                        {(["sender", "recipient"] as const).map((role) => {
                          const item =
                            data.transaction!.transfer_details![role]
                          return (
                            <div key={role} className="my-2">
                              <p>
                                {role === "sender" ? "Sender" : "Recipient"}:{" "}
                                {item.party.name}
                              </p>
                              <p>
                                Bank: {item.bank.text} · CLABE:{" "}
                                {item.account.text}
                              </p>
                              {item.party.qualifier && (
                                <p className="text-muted-foreground">
                                  The statement says this party name was not
                                  verified by the institution.
                                </p>
                              )}
                            </div>
                          )
                        })}
                        <p>
                          These are printed transfer fields. Review the
                          ownership links separately.
                        </p>
                      </div>
                    </Disclosure>
                  )}
                </DrawerSection>
                {canEdit && (
                  <div
                    className="flex flex-wrap gap-2"
                    role="group"
                    aria-label="Change this payment"
                  >
                    {data.ledger_status === "admitted" &&
                      !data.superseded_by_id && (
                        <Button
                          className="bg-[#b41624] text-white hover:bg-[#9a121f]"
                          onClick={() => setEditingLabels(true)}
                        >
                          Edit names and category
                        </Button>
                      )}
                    {data.ledger_status === "admitted" &&
                      !data.superseded_by_id && (
                        <Button
                          variant="outline"
                          onClick={() => setFinding(true)}
                        >
                          Create finding
                        </Button>
                      )}
                    {!correcting && (
                      <Button
                        variant="outline"
                        disabled={
                          data.ledger_status !== "admitted" ||
                          data.superseded_by_id !== null
                        }
                        onClick={() => setCorrecting(true)}
                      >
                        Correct a value
                      </Button>
                    )}
                    {onAdjudicate &&
                      data.ledger_status === "admitted" &&
                      data.superseded_by_id === null && (
                        <Button
                          variant="outline"
                          onClick={() => {
                            if (data.transaction) {
                              onClose()
                              onAdjudicate(data.transaction)
                            }
                          }}
                        >
                          Exclude from totals
                        </Button>
                      )}
                    {(data.ledger_status !== "admitted" ||
                      data.superseded_by_id !== null) && (
                      <p className="basis-full text-xs text-muted-foreground">
                        Only the current reading can be corrected.
                      </p>
                    )}
                  </div>
                )}
                {editingLabels && (
                  <PaymentLabelsEditor
                    key={transactionId}
                    caseId={caseId}
                    ids={[transactionId]}
                    names
                    onClose={() => setEditingLabels(false)}
                  />
                )}
                {correcting && (
                  <CorrectionForm
                    caseId={caseId}
                    transactionId={transactionId}
                    currency={data.transaction.currency}
                    initialRow={data.transaction}
                    initialDirection={
                      data.transaction.direction === "debit"
                        ? "debit"
                        : "credit"
                    }
                    onClose={() => {
                      setCorrecting(false)
                      void source.refetch()
                    }}
                  />
                )}
                <DrawerSection title="Linked">
                  <MoneyTrailReview
                    caseId={caseId}
                    transactionIds={[transactionId]}
                    label="Link transfer or follow this payment"
                  />
                  {allowNearby && (
                    <NearbyPaymentSearch
                      caseId={caseId}
                      row={data.transaction}
                    />
                  )}
                </DrawerSection>
              </section>
            )}
            {!data.transaction && (
              <>
                <p className="font-medium">
                  {data.ref_id} · {data.filename}
                </p>
                {data.ledger_status === "superseded" && (
                  <div className="space-y-2">
                    <p>This is the original transaction before correction.</p>
                    {data.superseded_by_id && (
                      <Button
                        variant="outline"
                        onClick={() => setReplacement(data.superseded_by_id)}
                      >
                        Open corrected transaction
                      </Button>
                    )}
                  </div>
                )}
                {data.locator_state === "missing" && (
                  <p>
                    No location was stored for this row. You can open the source
                    file.
                  </p>
                )}
                {data.locator_state === "invalid" && (
                  <p>
                    The stored location could not be read. You can open the
                    source file without a highlight.
                  </p>
                )}
                {data.locator_state === "stored" && (
                  <TransactionSourceHighlight
                    locatorPayload={data.locator}
                    sourceDocumentId={
                      data.filename.toLowerCase().endsWith(".pdf")
                        ? data.evidence_file_id
                        : undefined
                    }
                    valueLabel={data.ref_id}
                  />
                )}
                <Button onClick={() => setViewFile(true)}>
                  Open source file
                </Button>
              </>
            )}
            <TransactionNote
              caseId={caseId}
              transactionId={transactionId}
              refId={data.ref_id}
              fileId={data.evidence_file_id}
              filename={data.filename}
              locator={data.locator}
              initialOpen={initialNoteOpen}
              transaction={data.transaction}
            />
            <Disclosure label="File history and technical details">
              <SourceCustodyPanel
                caseId={caseId}
                fileId={data.evidence_file_id}
              />
              <p className="text-sm text-muted-foreground">{data.limitation}</p>
            </Disclosure>
            {assessAmount ? (
              <SourceAmountPanel
                key={`${caseId}:${data.evidence_file_id}`}
                caseId={caseId}
                evidenceId={data.evidence_file_id}
                onClose={() => setAssessAmount(false)}
              />
            ) : (
              <Button variant="outline" onClick={() => setAssessAmount(true)}>
                Assess an amount in source text
              </Button>
            )}
          </>
        )}
      </SourceFrame>
      {data && !source.isError && (
        <DocumentViewer
          caseId={caseId}
          evidenceId={data.evidence_file_id}
          open={viewFile}
          onOpenChange={setViewFile}
          documentUrl={evidenceAPI.getFileUrl(data.evidence_file_id)}
          documentName={data.filename}
          initialPage={page}
          navigationKey={`${caseId}:${transactionId}`}
        />
      )}
      {finding && (
        <InvestigatorFindingEditor
          caseId={caseId}
          ids={[transactionId]}
          onClose={() => setFinding(false)}
        />
      )}
    </>
  )
}

function SourceFrame({
  inline,
  open,
  onClose,
  children,
}: {
  inline: boolean
  open: boolean
  onClose: () => void
  children: ReactNode
}) {
  return inline ? (
    <aside
      aria-label="Selected payment and original source"
      className="finance-panel rounded-lg border p-4 space-y-4 min-w-0"
      data-finance-tone="info"
    >
      {children}
    </aside>
  ) : (
    <Dialog open={open} onOpenChange={(value) => !value && onClose()}>
      <DialogContent
        className="finance-panel sm:max-w-3xl max-h-[90vh] overflow-auto"
        data-finance-tone="info"
      >
        {children}
      </DialogContent>
    </Dialog>
  )
}
import { AccountOwnershipReview } from "./AccountOwnershipReview"
import { MoneyTrailReview } from "./MoneyTrailReview"

/** Dark header of the payment: amount, direction, date, account and how far the reading can be relied on. */
function PaymentHeader({
  transaction,
  ledgerStatus,
}: {
  transaction: LedgerTransaction
  ledgerStatus: string
}) {
  const amount = formatLedgerAmount(
    transaction.amount_minor,
    transaction.currency
  )
  const status = readLedgerStatus(ledgerStatus)
  const proof = readProofClass(transaction.proof_class)
  const layer = readExtractionLayer(transaction.extraction_layer)
  const directionWord =
    transaction.account_type === "credit_card"
      ? transaction.direction === "credit"
        ? "Card credit (reduces amount owed)"
        : "Card charge (increases amount owed)"
      : transaction.direction === "credit"
        ? "Money in"
        : transaction.direction === "debit"
          ? "Money out"
          : `Unknown direction: ${transaction.direction}`
  const statusTone =
    status.value === "admitted"
      ? "bg-[#e3f4ea] text-[#15653f]"
      : status.value === "superseded"
        ? "bg-[#f1eefb] text-[#573199]"
        : "bg-[#fde6e8] text-[#a3142a]"
  return (
    <div
      className="rounded-lg p-4 text-white space-y-2"
      style={{
        background:
          "radial-gradient(1100px 420px at 90% -20%, #3a1319 0%, #0b0c0f 62%)",
      }}
    >
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <span className="font-semibold uppercase tracking-wide text-[#c9cbd2]">
          Payment
        </span>
        <span
          className={`rounded-full px-2 py-0.5 font-semibold ${statusTone}`}
          title={status.description}
        >
          {status.label}
        </span>
      </div>
      {transaction.account_label && (
        <p className="text-sm text-[#c9cbd2]">{transaction.account_label}</p>
      )}
      <h3 className="font-semibold leading-snug">
        {transaction.description || "No description recorded"}
      </h3>
      <dl className="grid grid-cols-2 gap-3 text-sm">
        <div>
          <dt className="text-[#c9cbd2]">{directionWord}</dt>
          <dd
            className={`text-2xl font-semibold tabular-nums ${transaction.direction === "credit" ? "text-[#5fd39a]" : ""}`}
          >
            {amount.text} {transaction.currency}
          </dd>
          {!amount.scaled && (
            <dd className="mt-1 inline-block rounded bg-[#fdf0d5] px-2 py-0.5 text-xs font-semibold text-[#8a5300]">
              Unscaled: this figure is the stored count of minor units, not an
              amount. Read it against the source document before relying on it.
            </dd>
          )}
        </div>
        <div>
          <dt className="text-[#c9cbd2]">Date</dt>
          <dd>
            {transaction.ordering_date_context === "statement_end_ordering_only"
              ? "Date not printed"
              : transaction.ordering_date}
          </dd>
        </div>
      </dl>
      <p className="text-xs text-[#c9cbd2]">
        <span className="font-semibold text-white">{proof.label}</span>
        {": "}
        {proof.description} Read by:{" "}
        <span className="font-semibold text-white">
          {layer.label}
          {layer.isFallback ? " (marked fallback)" : ""}
        </span>
        . {layer.description}
      </p>
    </div>
  )
}

/** The judgement calls touching this payment, from the same lookup the rows use, with a way to all of them. */
function PaymentJudgements({
  caseId,
  transaction,
}: {
  caseId: string
  transaction: LedgerTransaction
}) {
  const lookup = useRowJudgementLookup()
  const count = lookup?.(transaction).length ?? 0
  if (!count) return null
  return (
    <DrawerSection
      title={`Judgement calls on this payment (${count})`}
      action={
        <a
          className="text-sm underline"
          href={`/cases/${caseId}/financial?${new URLSearchParams({ view: "statements", judgements: "1" })}`}
        >
          See all judgement calls →
        </a>
      }
    >
      <RowJudgementMarkers transaction={transaction} />
    </DrawerSection>
  )
}

function DrawerSection({
  title,
  action,
  children,
}: {
  title: string
  action?: ReactNode
  children: ReactNode
}) {
  return (
    <section className="space-y-2 border-t pt-3" aria-label={title}>
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          {title}
        </h4>
        {action}
      </div>
      {children}
    </section>
  )
}
