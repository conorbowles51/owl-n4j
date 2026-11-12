import { useCallback, useState, type ReactNode } from "react"
import { useQuery } from "@tanstack/react-query"
import { ChevronLeft, ChevronRight, X } from "lucide-react"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { EvidencePdfDocument } from "@/components/ui/evidence-pdf-document"
import { fetchAPI } from "@/lib/api-client"
import { cn } from "@/lib/cn"
import type { CoverageReview } from "../hooks/use-statement-coverage-review"
import { formatLedgerAmount } from "../lib/ledger-format"
import { compareFactsResponse, pageRange } from "../lib/statement-compare"

export type CompareCandidate = CoverageReview["candidates"][number]

/** One statement's figures for the facts strip. A null value is not known for that statement. */
export interface CompareFacts {
  institution: string
  account_number: string
  holder: string
  period_start: string
  period_end: string
  currency: string
  opening_balance_minor: string | null
  closing_balance_minor: string | null
  money_in_minor: string | null
  money_out_minor: string | null
  payment_count: number | null
  /** Short notes shown under the strip, e.g. why a total is not complete. */
  notes?: string[]
}

export interface CompareSide {
  fileId: string
  filename: string
  /** The PDF page this statement starts on. */
  startPage: number
  pages: number[]
  status: string
  facts: CompareFacts | null
}

const folded = (value: string) => value.trim().replace(/\s+/g, " ").toUpperCase()
const digitsOnly = (value: string) => value.replace(/[\s-]/g, "").toUpperCase()

type Verdict = "agrees" | "differs" | "unknown"

function verdict(left: string | null, right: string | null): Verdict {
  if (left === null || right === null || left === "" || right === "")
    return "unknown"
  return left === right ? "agrees" : "differs"
}

function money(value: string | null, currency: string) {
  if (value === null) return "Not known"
  return `${formatLedgerAmount(value, currency).text} ${currency}`
}

function factRows(own: CompareFacts, other: CompareFacts) {
  const sameCurrency = own.currency === other.currency
  const amount = (a: string | null, b: string | null): Verdict =>
    !sameCurrency ? (a === null || b === null ? "unknown" : "differs") : verdict(a, b)
  return [
    {
      label: "Bank",
      own: own.institution || "Not printed",
      other: other.institution || "Not printed",
      result: verdict(folded(own.institution), folded(other.institution)),
    },
    {
      label: "Account",
      own: own.account_number || "Not printed",
      other: other.account_number || "Not printed",
      result: verdict(digitsOnly(own.account_number), digitsOnly(other.account_number)),
    },
    {
      label: "Holder",
      own: own.holder || "Not printed",
      other: other.holder || "Not printed",
      result: verdict(folded(own.holder), folded(other.holder)),
    },
    {
      label: "Period",
      own: `${own.period_start || "?"} to ${own.period_end || "?"}`,
      other: `${other.period_start || "?"} to ${other.period_end || "?"}`,
      result:
        own.period_start && own.period_end && other.period_start && other.period_end
          ? own.period_start === other.period_start && own.period_end === other.period_end
            ? "agrees"
            : "differs"
          : "unknown",
    },
    {
      label: "Currency",
      own: own.currency || "Not known",
      other: other.currency || "Not known",
      result: verdict(own.currency, other.currency),
    },
    {
      label: "Opening balance",
      own: money(own.opening_balance_minor, own.currency),
      other: money(other.opening_balance_minor, other.currency),
      result: amount(own.opening_balance_minor, other.opening_balance_minor),
    },
    {
      label: "Closing balance",
      own: money(own.closing_balance_minor, own.currency),
      other: money(other.closing_balance_minor, other.currency),
      result: amount(own.closing_balance_minor, other.closing_balance_minor),
    },
    {
      label: "Money in",
      own: money(own.money_in_minor, own.currency),
      other: money(other.money_in_minor, other.currency),
      result: amount(own.money_in_minor, other.money_in_minor),
    },
    {
      label: "Money out",
      own: money(own.money_out_minor, own.currency),
      other: money(other.money_out_minor, other.currency),
      result: amount(own.money_out_minor, other.money_out_minor),
    },
    {
      label: "Number of payments",
      own: own.payment_count === null ? "Not known" : String(own.payment_count),
      other: other.payment_count === null ? "Not known" : String(other.payment_count),
      result: verdict(
        own.payment_count === null ? null : String(own.payment_count),
        other.payment_count === null ? null : String(other.payment_count)
      ),
    },
  ] as const
}

const verdictText: Record<Verdict, string> = {
  agrees: "Agrees",
  differs: "Differs",
  unknown: "Cannot compare",
}

function FactsStrip({
  own,
  other,
  otherState,
}: {
  own: CompareFacts | null
  other: CompareFacts | null
  otherState: string | null
}) {
  if (!own || !other)
    return (
      <section aria-label="Compared facts" className="text-sm">
        <p role="status">
          {otherState ?? "The figures for this statement are not available."}
        </p>
      </section>
    )
  const rows = factRows(own, other)
  const differs = rows.filter((row) => row.result === "differs").length
  const notes = [...(own.notes ?? []).map((n) => `This statement: ${n}`), ...(other.notes ?? []).map((n) => `Matching statement: ${n}`)]
  return (
    <section aria-label="Compared facts" className="min-w-0 space-y-2 text-sm">
      <p className="font-medium">
        {differs
          ? `${differs} of ${rows.length} facts differ.`
          : rows.every((row) => row.result === "agrees")
            ? `All ${rows.length} facts agree.`
            : `No fact differs; ${rows.filter((row) => row.result === "unknown").length} cannot be compared.`}
      </p>
      <table className="w-full table-fixed border-collapse text-left">
        <thead>
          <tr className="border-b text-xs text-muted-foreground">
            <th className="w-[26%] py-1 pr-2 font-normal">Fact</th>
            <th className="py-1 pr-2 font-normal">This statement</th>
            <th className="py-1 pr-2 font-normal">Matching statement</th>
            <th className="w-[22%] py-1 font-normal">Result</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.label} className="border-b align-top" data-result={row.result}>
              <th scope="row" className="py-1 pr-2 font-medium break-words">
                {row.label}
              </th>
              <td className="py-1 pr-2 break-words tabular-nums">{row.own}</td>
              <td className="py-1 pr-2 break-words tabular-nums">{row.other}</td>
              <td
                className={cn(
                  "py-1 break-words font-medium",
                  row.result === "differs" && "text-destructive",
                  row.result === "agrees" && "text-status-success",
                  row.result === "unknown" && "text-muted-foreground"
                )}
              >
                {verdictText[row.result]}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {notes.map((note) => (
        <p key={note} className="text-muted-foreground">
          {note}
        </p>
      ))}
    </section>
  )
}

function ComparePane({
  label,
  side,
  hidden,
}: {
  label: string
  side: CompareSide
  hidden: boolean
}) {
  const [page, setPage] = useState(side.startPage)
  const [total, setTotal] = useState<number | null>(null)
  const onPageCount = useCallback((_fileId: string, count: number) => setTotal(count), [])
  return (
    <section
      aria-label={label}
      className={cn("min-h-0 min-w-0 flex-1 flex-col rounded border", hidden ? "hidden md:flex" : "flex")}
    >
      <header className="shrink-0 space-y-0.5 border-b px-3 py-2 text-sm">
        <p className="text-xs font-medium uppercase text-muted-foreground">{label}</p>
        <p className="truncate font-semibold" title={side.filename}>
          {side.filename}
        </p>
        <p className="break-words">
          {side.facts
            ? `${side.facts.period_start || "?"} to ${side.facts.period_end || "?"}`
            : ""}
          {side.facts ? " · " : ""}
          {pageRange(side.pages, side.startPage)} · {side.status}
        </p>
        <div className="flex items-center gap-1 pt-1">
          <Button
            variant="ghost"
            size="icon-sm"
            aria-label={`Previous page of ${label.toLowerCase()}`}
            disabled={page <= 1}
            onClick={() => setPage((value) => Math.max(1, value - 1))}
          >
            <ChevronLeft className="size-4" />
          </Button>
          <span className="min-w-[90px] text-center text-xs text-muted-foreground">
            Page {page}
            {total ? ` of ${total}` : ""}
          </span>
          <Button
            variant="ghost"
            size="icon-sm"
            aria-label={`Next page of ${label.toLowerCase()}`}
            disabled={total !== null && page >= total}
            onClick={() => setPage((value) => value + 1)}
          >
            <ChevronRight className="size-4" />
          </Button>
          {page !== side.startPage && (
            <Button variant="link" size="sm" onClick={() => setPage(side.startPage)}>
              Back to page {side.startPage}
            </Button>
          )}
        </div>
      </header>
      <div className="min-h-0 flex-1">
        <EvidencePdfDocument
          evidenceId={side.fileId}
          page={page}
          onPageCount={onPageCount}
          onVisiblePageChange={setPage}
        />
      </div>
    </section>
  )
}

/**
 * This statement next to the statement it may copy: both PDFs at their own first pages, each with its own
 * scrolling, paging and zoom, the facts the match rests on, and the duplicate decision. Closing is only ever the
 * person's own choice; deciding inside the view leaves it open.
 */
export function StatementCompareView({
  caseId,
  own,
  other,
  open,
  onOpenChange,
  decision,
}: {
  caseId: string
  own: CompareSide
  other: CompareCandidate
  open: boolean
  onOpenChange: (open: boolean) => void
  /** The duplicate decision controls, the same ones the statement screen shows. */
  decision?: ReactNode
}) {
  const [shown, setShown] = useState<"own" | "other">("own")
  const imported = other.status === "imported" && !!other.source_document_id
  const facts = useQuery({
    queryKey: ["statement-compare-facts", caseId, other.source_document_id],
    enabled: open && imported,
    retry: false,
    queryFn: async () => {
      const parsed = compareFactsResponse.parse(
        await fetchAPI(
          `/api/financial/statement-import/sources/${encodeURIComponent(other.source_document_id!)}/compare-facts?${new URLSearchParams({ case_id: caseId })}`
        )
      )
      if (parsed.case_id !== caseId || parsed.evidence_file_id !== other.file_id)
        throw new Error("The matching statement's figures could not be verified for this case.")
      return parsed
    },
  })
  const otherFacts: CompareFacts | null = facts.data
    ? {
        institution: facts.data.institution,
        account_number: facts.data.account_number,
        holder: facts.data.holder,
        period_start: facts.data.period_start,
        period_end: facts.data.period_end,
        currency: facts.data.currency,
        opening_balance_minor: facts.data.opening_balance_minor,
        closing_balance_minor: facts.data.closing_balance_minor,
        money_in_minor: facts.data.mixed_currency ? null : facts.data.money_in_minor,
        money_out_minor: facts.data.mixed_currency ? null : facts.data.money_out_minor,
        payment_count: facts.data.payment_count,
        notes: [
          ...(facts.data.held_from_ledger
            ? [`${facts.data.held_from_ledger} more payments are held out of the ledger and are not counted here.`]
            : []),
          ...(facts.data.mixed_currency
            ? ["Its payments are in more than one currency, so money in and out are not totalled."]
            : []),
        ],
      }
    : null
  const otherState = !imported
    ? "The matching statement is not imported yet, so its stored figures are not available. Compare the pages below."
    : facts.isPending
      ? "Loading the matching statement's figures…"
      : facts.error
        ? `${facts.error.message} Compare the pages below.`
        : null
  const otherSide: CompareSide = {
    fileId: other.file_id,
    filename: facts.data?.filename || other.filename,
    startPage: facts.data?.pages[0] ?? other.page_number ?? 1,
    pages: facts.data?.pages ?? [],
    status: other.status === "imported" ? "Already imported" : "Awaiting import",
    facts: otherFacts ?? {
      institution: "",
      account_number: "",
      holder: "",
      period_start: other.period_start,
      period_end: other.period_end,
      currency: "",
      opening_balance_minor: null,
      closing_balance_minor: null,
      money_in_minor: null,
      money_out_minor: null,
      payment_count: null,
    },
  }
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        showCloseButton={false}
        className="flex h-[95dvh] w-[calc(100vw-1rem)] max-w-[calc(100vw-1rem)] flex-col gap-0 overflow-hidden p-0 sm:max-w-[calc(100vw-2rem)] sm:w-[calc(100vw-2rem)]"
      >
        <DialogHeader className="flex-row items-center justify-between gap-2 space-y-0 border-b px-4 py-3">
          <div className="min-w-0">
            <DialogTitle className="text-base">Compare side by side</DialogTitle>
            <DialogDescription className="break-words text-xs">
              {own.filename} and {otherSide.filename}
            </DialogDescription>
          </div>
          <Button variant="ghost" size="sm" onClick={() => onOpenChange(false)} aria-label="Close comparison">
            <X className="size-4" />
            <span className="hidden sm:inline">Close</span>
          </Button>
        </DialogHeader>
        <div className="max-h-[42%] min-h-0 shrink-0 space-y-3 overflow-y-auto overflow-x-hidden border-b px-4 py-3">
          <FactsStrip own={own.facts} other={otherFacts} otherState={otherState} />
          {decision && (
            <section aria-label="Decision in the comparison" className="min-w-0 space-y-2">
              {decision}
            </section>
          )}
        </div>
        <div
          role="group"
          aria-label="Choose a document"
          className="flex shrink-0 gap-2 border-b px-4 py-2 md:hidden"
        >
          <Button
            size="sm"
            variant={shown === "own" ? "primary" : "outline"}
            aria-pressed={shown === "own"}
            onClick={() => setShown("own")}
          >
            This statement
          </Button>
          <Button
            size="sm"
            variant={shown === "other" ? "primary" : "outline"}
            aria-pressed={shown === "other"}
            onClick={() => setShown("other")}
          >
            Matching statement
          </Button>
        </div>
        <div className="flex min-h-0 min-w-0 flex-1 gap-2 overflow-hidden p-2">
          <ComparePane
            key={`own:${own.fileId}:${own.startPage}`}
            label="This statement"
            side={own}
            hidden={shown !== "own"}
          />
          <ComparePane
            key={`other:${otherSide.fileId}:${otherSide.startPage}`}
            label="Matching statement"
            side={otherSide}
            hidden={shown !== "other"}
          />
        </div>
      </DialogContent>
    </Dialog>
  )
}
