/**
 * The relational ledger, as rows on a screen.
 *
 * This is the first thing in the frontend that renders a `LedgerTransaction`.
 * It is presentational on purpose: it takes rows and draws them, and knows
 * nothing about fetching, so every case below can be put in front of it
 * directly rather than staged through a query. `LedgerPanel` is the half that
 * fetches.
 *
 * Three things here are correctness rather than presentation, and each exists
 * because the alternative silently misleads a reader looking at money.
 *
 * **An unscaled amount is marked.** `formatLedgerAmount` returns
 * `scaled: false` when it could not turn a stored minor-unit count into a
 * figure, and its own docstring is explicit that a caller which renders that
 * without saying so is showing 123456 where 1,234.56 belongs. So the marker
 * here is not decoration; dropping it turns a hundredfold error into a
 * plausible number.
 *
 * **An absent running balance is stated, not blank.** `running_balance_minor`
 * is nullable and an empty cell reads as zero, or as a balance of nothing,
 * neither of which is what null means.
 *
 * **An unrecognised vocabulary member is shown, loudly.** Every closed
 * vocabulary arrives as a bare string or int and is narrowed at runtime, so a
 * backend one version ahead of this build can send a member this build has
 * never heard of. Those rows still render, still show the raw value, and are
 * marked as unread rather than left blank, because a blank badge on a
 * financial row reads as an answer.
 *
 * Rows are drawn in the order they arrive. The ledger read orders by
 * `ordering_date` then `row_index` — the second of those is what keeps a
 * statement's own printed sequence intact where a day holds several movements
 * — so re-sorting here would throw away an ordering the backend established
 * deliberately.
 *
 * The zero-row case draws a single sentence rather than a bare header. In
 * practice `LedgerPanel` catches that case first and says more about it; this
 * is the standalone guard, so the component is never a header over nothing.
 */

import { CircleHelp, TriangleAlert } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"

import type { LedgerTransaction } from "../api"
import {
  formatLedgerAmount,
  readDateSource,
  readDirection,
  readExtractionLayer,
  readLedgerStatus,
  readProofClass,
  readQuarantineReason,
  type NarrowedTerm,
} from "../lib/ledger-format"

type BadgeVariant =
  | "default"
  | "secondary"
  | "destructive"
  | "outline"
  | "success"
  | "danger"
  | "warning"
  | "info"
  | "amber"
  | "slate"

/** Reserved for "this build cannot read this value", and used for nothing else. */
const UNRECOGNISED_VARIANT: BadgeVariant = "warning"

const STATUS_VARIANTS: Record<string, BadgeVariant> = {
  admitted: "success",
  quarantined: "amber",
  superseded: "slate",
  rejected: "danger",
}

const PROOF_CLASS_VARIANTS: Record<string, BadgeVariant> = {
  p0: "info",
  p1: "info",
  p2: "info",
  p3: "amber",
  p4: "danger",
}

const DIRECTION_VARIANTS: Record<string, BadgeVariant> = {
  credit: "info",
  debit: "slate",
}

/**
 * Outline throughout: the reason sits beside the status badge that already
 * carries the colour, and a second filled badge would read as a second status.
 */
const QUARANTINE_REASON_VARIANTS: Record<string, BadgeVariant> = {
  balance_break: "outline",
  unreadable_row: "outline",
  currency_mismatch: "outline",
  unexplained_delta: "outline",
  adjudicated: "outline",
}

/**
 * One narrowed value as a badge.
 *
 * `data-unrecognised` carries the distinction the colour also makes, so a test
 * asserts on the narrowing rather than on a class name.
 */
function TermBadge({
  term,
  variants,
  testId,
}: {
  term: NarrowedTerm<string>
  variants: Record<string, BadgeVariant>
  testId: string
}) {
  const unrecognised = term.value === null
  return (
    <Badge
      variant={unrecognised ? UNRECOGNISED_VARIANT : variants[term.value!]}
      title={term.description}
      data-testid={testId}
      data-unrecognised={unrecognised ? "true" : "false"}
    >
      {unrecognised && <CircleHelp aria-hidden="true" />}
      {term.label}
    </Badge>
  )
}

function LedgerRow({ transaction }: { transaction: LedgerTransaction }) {
  const amount = formatLedgerAmount(transaction.amount_minor, transaction.currency)
  const direction = readDirection(transaction.direction)
  const status = readLedgerStatus(transaction.ledger_status)
  const proofClass = readProofClass(transaction.proof_class)
  const layer = readExtractionLayer(transaction.extraction_layer)
  const dateSource = readDateSource(transaction.ordering_date_source)
  const quarantineReason =
    transaction.quarantine_reason === null
      ? null
      : readQuarantineReason(transaction.quarantine_reason)

  const balance =
    transaction.running_balance_minor === null
      ? null
      : formatLedgerAmount(transaction.running_balance_minor, transaction.currency)

  return (
    <TableRow data-testid="ledger-row" data-row-key={transaction.key}>
      <TableCell className="align-top whitespace-nowrap">
        <div className="font-mono text-xs">{transaction.ordering_date}</div>
        <Badge
          variant={dateSource.value === null ? UNRECOGNISED_VARIANT : "outline"}
          title={dateSource.description}
          data-testid="ledger-date-source"
          data-unrecognised={dateSource.value === null ? "true" : "false"}
          className="mt-1"
        >
          {dateSource.value === null && <CircleHelp aria-hidden="true" />}
          {dateSource.label}
        </Badge>
      </TableCell>

      <TableCell className="align-top">
        {transaction.description === null ? (
          <span
            className="text-xs text-muted-foreground italic"
            data-testid="ledger-no-description"
            title="The ledger holds no description for this row."
          >
            No description recorded
          </span>
        ) : (
          <span className="text-sm">{transaction.description}</span>
        )}
        {transaction.counterparty_raw !== null && (
          <div
            className="text-xs text-muted-foreground"
            data-testid="ledger-counterparty"
          >
            {transaction.counterparty_raw}
          </div>
        )}
        {transaction.bank_reference !== null && (
          <div
            className="font-mono text-xs text-muted-foreground"
            data-testid="ledger-bank-reference"
            title="The reference the bank printed against this movement."
          >
            {transaction.bank_reference}
          </div>
        )}
      </TableCell>

      <TableCell className="align-top">
        <TermBadge
          term={direction}
          variants={DIRECTION_VARIANTS}
          testId="ledger-direction"
        />
      </TableCell>

      <TableCell className="align-top text-right whitespace-nowrap">
        <span className="font-mono text-sm tabular-nums" data-testid="ledger-amount">
          {amount.text}
        </span>{" "}
        <span className="text-xs text-muted-foreground">{amount.currency}</span>
        {!amount.scaled && (
          <div>
            <Badge
              variant="warning"
              data-testid="ledger-amount-unscaled"
              title={
                "This figure is the stored count of minor units, not an amount. " +
                "It could not be scaled, so read it against the source document " +
                "before relying on it."
              }
            >
              <TriangleAlert aria-hidden="true" />
              Unscaled
            </Badge>
          </div>
        )}
      </TableCell>

      <TableCell className="align-top text-right whitespace-nowrap">
        {balance === null ? (
          <span
            className="text-xs text-muted-foreground italic"
            data-testid="ledger-no-balance"
            title="The ledger holds no running balance for this row."
          >
            No running balance
          </span>
        ) : (
          <>
            <span
              className="font-mono text-sm tabular-nums"
              data-testid="ledger-balance"
            >
              {balance.text}
            </span>
            {!balance.scaled && (
              <div>
                <Badge
                  variant="warning"
                  data-testid="ledger-balance-unscaled"
                  title={
                    "This figure is the stored count of minor units, not an " +
                    "amount. It could not be scaled."
                  }
                >
                  <TriangleAlert aria-hidden="true" />
                  Unscaled
                </Badge>
              </div>
            )}
          </>
        )}
      </TableCell>

      <TableCell className="align-top">
        <div className="flex flex-col items-start gap-1">
          <TermBadge
            term={proofClass}
            variants={PROOF_CLASS_VARIANTS}
            testId="ledger-proof-class"
          />
          <Badge
            variant={
              layer.value === null
                ? UNRECOGNISED_VARIANT
                : layer.isFallback
                  ? "amber"
                  : "slate"
            }
            title={layer.description}
            data-testid="ledger-extraction-layer"
            data-unrecognised={layer.value === null ? "true" : "false"}
            data-fallback={layer.isFallback ? "true" : "false"}
          >
            {layer.value === null && <CircleHelp aria-hidden="true" />}
            {layer.label}
          </Badge>
        </div>
      </TableCell>

      <TableCell className="align-top">
        <div className="flex flex-col items-start gap-1">
          <TermBadge
            term={status}
            variants={STATUS_VARIANTS}
            testId="ledger-status"
          />
          {quarantineReason !== null && (
            <TermBadge
              term={quarantineReason}
              variants={QUARANTINE_REASON_VARIANTS}
              testId="ledger-quarantine-reason"
            />
          )}
          {transaction.superseded_by_id !== null && (
            <span
              className="text-xs text-muted-foreground"
              data-testid="ledger-superseded-by"
              title="A later row replaced this one. The later row is the one that counts."
            >
              Replaced by a later row
            </span>
          )}
        </div>
      </TableCell>
    </TableRow>
  )
}

const COLUMN_COUNT = 7

export function LedgerTable({
  transactions,
}: {
  transactions: LedgerTransaction[]
}) {
  return (
    <Table data-testid="ledger-table">
      <TableHeader>
        <TableRow>
          <TableHead>Date</TableHead>
          <TableHead>Description</TableHead>
          <TableHead>Direction</TableHead>
          <TableHead className="text-right">Amount</TableHead>
          <TableHead className="text-right">Running balance</TableHead>
          <TableHead>How it was read</TableHead>
          <TableHead>Status</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {transactions.length === 0 ? (
          <TableRow>
            <TableCell
              colSpan={COLUMN_COUNT}
              className="text-center text-sm text-muted-foreground"
              data-testid="ledger-table-empty"
            >
              No ledger rows to show.
            </TableCell>
          </TableRow>
        ) : (
          transactions.map((transaction) => (
            <LedgerRow key={transaction.key} transaction={transaction} />
          ))
        )}
      </TableBody>
    </Table>
  )
}
