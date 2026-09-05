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
 * **The grounds for a quarantine are a column only when the list is about
 * them.** `showQuarantineGrounds` promotes `quarantine_reason` out of the
 * status cell into a column of its own, which is what a list filtered to
 * quarantined rows needs and what a mixed list does not. It is a flag on this
 * component rather than a second component because the five cells to its left
 * are where the three rules above live: a second table would be a second copy
 * of them, and the copy is what drifts. The status column stays either way,
 * since a row that is somehow not quarantined in a quarantined list is exactly
 * the thing a reader must be able to see.
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
  readQuarantineGrounds,
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
 * Outline throughout, in both positions. Stacked under the status badge, a
 * second filled badge would read as a second status. Promoted to its own
 * column, the list is filtered to one status anyway, so colouring the reason
 * would rank the five against each other — and they are five different things
 * that happened, not a scale. The distinction that does matter, a person
 * against a check, is carried in words beside the badge rather than in a hue.
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

/**
 * The grounds cell, drawn only when the table was told to show it.
 *
 * A quarantined row without grounds says so rather than leaving the cell
 * empty, on the same rule as the absent running balance: an empty cell in a
 * column headed "Grounds" reads as "none needed".
 *
 * `data-decided-by-person` is three-valued and carries the distinction the
 * sentence also makes, so a test asserts on the classification rather than on
 * prose that may be reworded.
 */
function GroundsCell({ transaction }: { transaction: LedgerTransaction }) {
  if (transaction.quarantine_reason === null) {
    return (
      <TableCell className="align-top">
        <span
          className="text-xs text-muted-foreground italic"
          data-testid="ledger-no-grounds"
          title="The ledger records no quarantine reason for this row."
        >
          No grounds recorded
        </span>
      </TableCell>
    )
  }

  const grounds = readQuarantineGrounds(transaction.quarantine_reason)
  return (
    <TableCell className="align-top">
      <div className="flex flex-col items-start gap-1">
        <TermBadge
          term={grounds}
          variants={QUARANTINE_REASON_VARIANTS}
          testId="ledger-quarantine-reason"
        />
        <span
          className="text-xs text-muted-foreground"
          data-testid="ledger-grounds-origin"
          data-decided-by-person={
            grounds.decidedByPerson === null
              ? "unknown"
              : grounds.decidedByPerson
                ? "true"
                : "false"
          }
          title={grounds.origin}
        >
          {grounds.decidedByPerson === null
            ? "Established by something this build cannot name"
            : grounds.decidedByPerson
              ? "Decided by a person"
              : "Established by a check"}
        </span>
      </div>
    </TableCell>
  )
}

function LedgerRow({
  transaction,
  showQuarantineGrounds,
}: {
  transaction: LedgerTransaction
  showQuarantineGrounds: boolean
}) {
  const amount = formatLedgerAmount(transaction.amount_minor, transaction.currency)
  const direction = readDirection(transaction.direction)
  const status = readLedgerStatus(transaction.ledger_status)
  const proofClass = readProofClass(transaction.proof_class)
  const layer = readExtractionLayer(transaction.extraction_layer)
  const dateSource = readDateSource(transaction.ordering_date_source)
  const quarantineReason =
    transaction.quarantine_reason === null || showQuarantineGrounds
      ? null
      : readQuarantineGrounds(transaction.quarantine_reason)

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

      {showQuarantineGrounds && <GroundsCell transaction={transaction} />}
    </TableRow>
  )
}

/** Date, description, direction, amount, balance, how it was read, status. */
const BASE_COLUMN_COUNT = 7

export function LedgerTable({
  transactions,
  showQuarantineGrounds = false,
}: {
  transactions: LedgerTransaction[]
  showQuarantineGrounds?: boolean
}) {
  const columnCount = BASE_COLUMN_COUNT + (showQuarantineGrounds ? 1 : 0)

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
          {showQuarantineGrounds && <TableHead>Grounds</TableHead>}
        </TableRow>
      </TableHeader>
      <TableBody>
        {transactions.length === 0 ? (
          <TableRow>
            <TableCell
              colSpan={columnCount}
              className="text-center text-sm text-muted-foreground"
              data-testid="ledger-table-empty"
            >
              No ledger rows to show.
            </TableCell>
          </TableRow>
        ) : (
          transactions.map((transaction) => (
            <LedgerRow
              key={transaction.key}
              transaction={transaction}
              showQuarantineGrounds={showQuarantineGrounds}
            />
          ))
        )}
      </TableBody>
    </Table>
  )
}
