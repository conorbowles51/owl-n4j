/**
 * Reading a bank file to the reader, then storing it if they say so.
 *
 * This is the half `ProcessHoldDialog` says is missing.  The gate identifies a
 * native bank file and refuses to send it to the document pipeline, correctly,
 * and until now that was the end of the road: the file was held and had
 * nowhere to go.  This is where it goes.
 *
 * Three steps, and the middle one is the point
 * --------------------------------------------
 *
 * Ask for the period, read the file, store it.  The read stores nothing, which
 * is why it is a step of its own rather than a spinner inside the write.  A
 * bank file is not something a person can eyeball before committing it, so the
 * only chance to see what is about to enter the ledger is a reading that
 * happens first and keeps nothing.  Both steps go through the same parser on
 * the backend, so what step two shows is what step three would store.
 *
 * What it is not is a promise.  Three of the twelve things the write can
 * answer are decided against rows already in the ledger rather than against
 * this file, and no amount of reading these bytes would find them.  So step
 * three renders its own answer in full rather than assuming step two settled
 * it.
 *
 * Why the dates are asked for
 * ---------------------------
 *
 * Three of the four bank formats print years with two digits and none of them
 * carries the century.  There is no correct default: a case has no date range
 * to borrow, and choosing one silently decides which decade a statement
 * belongs to in the one place the document is no help.  Both fields start
 * empty and the button stays disabled until they are filled, which costs one
 * moment and buys a statement that is filed under the right decade or not at
 * all.
 *
 * Everything else about the window is the endpoint's rule to enforce.  A
 * second copy of it here would be a second thing to keep in step, so a range
 * this screen cannot fault is sent and the endpoint's own answer is shown.
 */

import { useState } from "react"
import { FileText } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { LoadingSpinner } from "@/components/ui/loading-spinner"
import { usePrecheckFile, useIngestFile } from "../hooks/use-ledger-ingest"
import {
  accountLabel,
  didStore,
  formatPeriodRange,
  ingestVariant,
  precheckVariant,
  readIngestOutcome,
  readPrecheckOutcome,
  wouldStore,
} from "../lib/ingest-format"
import { formatLedgerAmount } from "../lib/ledger-format"
import type { FilePrecheck } from "../api"

interface SendToLedgerDialogProps {
  caseId: string
  fileId: string
  /** Null when the file has no name. The id stands in, as it does on the list. */
  fileName: string | null
  open: boolean
  onClose: () => void
}

/**
 * One account as the file introduces it.
 *
 * The balances are the reason this is a block and not a line.  A statement
 * that prints an opening and a closing balance can be checked against its own
 * arithmetic later; one that prints neither cannot, and that difference is
 * worth seeing before the rows are stored rather than after.  An absent
 * balance is left absent: rendering it as zero would turn a fact the file did
 * not state into one it did.
 */
function AccountSummary({ account }: { account: FilePrecheck["accounts"][number] }) {
  const period = account.period
  const range = period ? formatPeriodRange(period.start, period.end) : null

  const balance = (
    label: string,
    side: { amount_minor: number | null; currency: string | null }
  ) => {
    // Absent stays absent. A null amount means the file printed no balance,
    // which is not the same as a balance of zero and must never read as one.
    if (side.amount_minor === null) return null
    const code = side.currency ?? period?.currency
    // A figure with no currency is not a figure anyone can act on, and
    // scaling it would require guessing how many minor units make a unit.
    // The account still lists its rows and its period; only this line drops.
    if (!code) return null
    const money = formatLedgerAmount(side.amount_minor, code)
    return `${label} ${money.text} ${money.currency}`
  }

  const balances = period
    ? [balance("Opening", period.opening), balance("Closing", period.closing)].filter(
        (line): line is string => line !== null
      )
    : []

  return (
    <div
      className="rounded-md border border-border/70 bg-muted/30 p-3"
      data-testid="precheck-account"
    >
      <div className="flex items-start justify-between gap-2">
        <span className="min-w-0 flex-1 truncate text-sm font-medium">
          {accountLabel(account)}
        </span>
        <span className="shrink-0 text-xs text-muted-foreground">
          {account.row_count} row{account.row_count === 1 ? "" : "s"}
        </span>
      </div>
      {account.institution_name && (
        <p className="mt-1 text-xs text-muted-foreground">{account.institution_name}</p>
      )}
      {/* No period is the normal case for one of the four formats, so its
          absence is left unremarked rather than reported as a gap. */}
      {range && <p className="mt-1 text-xs text-muted-foreground">{range}</p>}
      {balances.length > 0 && (
        <p className="mt-1 text-xs text-muted-foreground">{balances.join(" / ")}</p>
      )}
    </div>
  )
}

export function SendToLedgerDialog({
  caseId,
  fileId,
  fileName,
  open,
  onClose,
}: SendToLedgerDialogProps) {
  const [windowStart, setWindowStart] = useState("")
  const [windowEnd, setWindowEnd] = useState("")
  const [defaultCurrency, setDefaultCurrency] = useState("")

  const precheck = usePrecheckFile(caseId)
  const ingest = useIngestFile(caseId)

  const reading = precheck.data
  const written = ingest.data
  const busy = precheck.isPending || ingest.isPending

  const reset = () => {
    precheck.reset()
    ingest.reset()
    setWindowStart("")
    setWindowEnd("")
    setDefaultCurrency("")
  }

  const close = () => {
    // Cleared on the way out rather than on the way in, so a dialog reopened
    // for a different file cannot show the previous file's reading for the
    // frame before the new one arrives.
    reset()
    onClose()
  }

  const params = {
    fileId,
    windowStart,
    windowEnd,
    defaultCurrency: defaultCurrency.trim() || undefined,
  }

  const handleRead = () => {
    // The mutation reports its own failure through `error`; nothing is thrown
    // at the caller, so there is no rejection to handle here.
    precheck.mutate(params)
  }

  const handleStore = () => {
    ingest.mutate(params)
  }

  const canRead = Boolean(windowStart && windowEnd) && !busy

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        // A write in flight is not interruptible by dismissing the thing
        // watching it, so escape and the overlay are ignored while it runs.
        if (!next && !busy) close()
      }}
    >
      <DialogContent className="sm:max-w-xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <FileText className="size-4 text-muted-foreground" />
            Send to ledger
          </DialogTitle>
          <DialogDescription>
            <span className="font-medium">{fileName ?? fileId}</span> is a bank file.
            Reading it here shows what it holds before anything is stored.
          </DialogDescription>
        </DialogHeader>

        <div className="max-h-[26rem] space-y-4 overflow-y-auto pr-1">
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="ledger-window-start">Evidence from</Label>
              <Input
                id="ledger-window-start"
                data-testid="window-start"
                type="date"
                value={windowStart}
                disabled={busy}
                onChange={(e) => setWindowStart(e.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="ledger-window-end">Evidence to</Label>
              <Input
                id="ledger-window-end"
                data-testid="window-end"
                type="date"
                value={windowEnd}
                disabled={busy}
                onChange={(e) => setWindowEnd(e.target.value)}
              />
            </div>
          </div>
          <p className="text-xs text-muted-foreground">
            Some bank files write years with two digits, so the period this matter
            covers is what decides whether a statement is from 1998 or 2098. Give the
            widest range the evidence could fall in.
          </p>

          <div className="space-y-1.5">
            <Label htmlFor="ledger-currency">Currency, if the file does not say</Label>
            <Input
              id="ledger-currency"
              data-testid="default-currency"
              placeholder="Leave blank unless you know"
              value={defaultCurrency}
              disabled={busy}
              onChange={(e) => setDefaultCurrency(e.target.value)}
            />
            <p className="text-xs text-muted-foreground">
              Only used where the file prints no currency of its own. A wrong answer
              here produces amounts that look right, so leave it blank if unsure.
            </p>
          </div>

          {precheck.error && (
            <p
              className="rounded-md border border-destructive/40 bg-destructive/5 p-3 text-xs"
              data-testid="precheck-error"
            >
              {precheck.error.message}
            </p>
          )}

          {reading && !written && <PrecheckReport precheck={reading} />}

          {written && (
            <div
              className="rounded-md border border-border/70 bg-muted/30 p-3"
              data-testid="ingest-report"
            >
              {(() => {
                const term = readIngestOutcome(written.outcome)
                return (
                  <>
                    <Badge variant={ingestVariant(term)} className="text-[10px]">
                      {term.label}
                    </Badge>
                    <p className="mt-2 text-xs text-muted-foreground">{term.description}</p>
                    {didStore(written) && (
                      <p className="mt-1 text-xs text-muted-foreground">
                        {written.transactions_stored} transaction
                        {written.transactions_stored === 1 ? "" : "s"} added.
                        {written.unlinked_rows > 0 &&
                          ` ${written.unlinked_rows} row${
                            written.unlinked_rows === 1 ? "" : "s"
                          } could not be attached to an account and were set aside.`}
                      </p>
                    )}
                    {/* The endpoint's own words, kept because they name the
                        specific thing rather than the category of thing. */}
                    {written.reason && (
                      <p className="mt-1 text-xs text-muted-foreground">{written.reason}</p>
                    )}
                  </>
                )
              })()}
            </div>
          )}

          {ingest.error && (
            <p
              className="rounded-md border border-destructive/40 bg-destructive/5 p-3 text-xs"
              data-testid="ingest-error"
            >
              {ingest.error.message}
            </p>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={close} disabled={busy}>
            {written ? "Done" : "Cancel"}
          </Button>
          {!written && !reading && (
            <Button onClick={handleRead} disabled={!canRead} data-testid="read-file">
              {precheck.isPending && <LoadingSpinner className="mr-1.5 size-3.5" />}
              Read the file
            </Button>
          )}
          {!written && reading && (
            <>
              <Button
                variant="outline"
                onClick={() => precheck.reset()}
                disabled={busy}
                data-testid="read-again"
              >
                Change dates
              </Button>
              {wouldStore(reading) && (
                <Button onClick={handleStore} disabled={busy} data-testid="store-file">
                  {ingest.isPending && <LoadingSpinner className="mr-1.5 size-3.5" />}
                  Add to ledger
                </Button>
              )}
            </>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

/**
 * What the reading found, in the order a person checks it.
 *
 * The outcome first, because it governs whether the rest matters.  Then the
 * counts, then the accounts, then the rows that could not be attached to one.
 * Unattached rows are last and stated plainly: they are the reason a file that
 * parsed cleanly can still be refused, and burying them under the account list
 * would hide the one thing that stops the write.
 */
function PrecheckReport({ precheck }: { precheck: FilePrecheck }) {
  const term = readPrecheckOutcome(precheck.outcome)

  return (
    <div
      className="space-y-3 rounded-md border border-border/70 bg-muted/30 p-3"
      data-testid="precheck-report"
    >
      <div className="flex items-center gap-2">
        <Badge variant={precheckVariant(term)} className="text-[10px]">
          {term.label}
        </Badge>
        {precheck.detected_format && (
          <span className="text-xs text-muted-foreground">{precheck.detected_format}</span>
        )}
      </div>
      <p className="text-xs text-muted-foreground">{term.description}</p>
      {precheck.reason && (
        <p className="text-xs text-muted-foreground">{precheck.reason}</p>
      )}

      {precheck.row_count !== null && (
        <p className="text-xs text-muted-foreground" data-testid="precheck-rows">
          {precheck.parsed_row_count ?? precheck.row_count} of {precheck.row_count} row
          {precheck.row_count === 1 ? "" : "s"} read
          {precheck.skipped.length > 0 &&
            `, ${precheck.skipped.length} skipped`}
          .
        </p>
      )}

      {formatPeriodRange(
        precheck.earliest_ordering_date,
        precheck.latest_ordering_date
      ) && (
        <p className="text-xs text-muted-foreground" data-testid="precheck-span">
          Covering{" "}
          {formatPeriodRange(
            precheck.earliest_ordering_date,
            precheck.latest_ordering_date
          )}
          .
        </p>
      )}

      {precheck.accounts.length > 0 && (
        <div className="space-y-2">
          {precheck.accounts.map((account, index) => (
            <AccountSummary key={account.account_key ?? index} account={account} />
          ))}
        </div>
      )}

      {precheck.unattributed_row_count > 0 && (
        <p className="text-xs text-muted-foreground" data-testid="precheck-unattributed">
          {precheck.unattributed_row_count} row
          {precheck.unattributed_row_count === 1 ? "" : "s"} name an account this file
          never introduces, so there is no way to say whose money moved. Nothing will
          be stored until that is resolved.
        </p>
      )}
    </div>
  )
}
