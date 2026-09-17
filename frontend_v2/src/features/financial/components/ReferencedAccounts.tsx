import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { z } from "zod"
import { Landmark, RefreshCw } from "lucide-react"
import { fetchAPI } from "@/lib/api-client"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { useFinancialAccess } from "../hooks/use-financial-access"
import { InvestigatorFindingEditor } from "./InvestigatorFindingEditor"
import { SelectedPaymentsReview } from "./SelectedPaymentsReview"
import { LedgerSourceDialog } from "./LedgerSourceDialog"
import { AccountStatementReview } from "./AccountStatementReview"
import type { AccountReviewDates } from "./AccountStatementReview"

const reference = z.object({
  id: z.string(),
  reference: z.string(),
  kind: z.string(),
  partial: z.boolean(),
  status: z.enum(["no_statement_found", "possible_statement"]),
  variants: z.array(z.string()),
  payment_ids: z.array(z.string()),
  payment_count: z.number(),
  examples: z.array(
    z.object({
      payment_id: z.string(),
      text: z.string(),
      start: z.number(),
      end: z.number(),
    })
  ),
  possible_accounts: z.array(
    z.object({
      account_id: z.string(),
      reference: z.string(),
      holder: z.string().nullable(),
      bank: z.string().nullable(),
      statement_count: z.number(),
    })
  ),
})
const response = z.object({
  case_id: z.string(),
  revision: z.string(),
  offset: z.number(),
  limit: z.number(),
  total: z.number(),
  scanned_payments: z.number(),
  missing_count: z.number(),
  possible_match_count: z.number(),
  items: z.array(reference),
})
type Reference = z.infer<typeof reference>

export function ReferencedAccounts({
  caseId,
  onOpenTransactions,
}: {
  caseId: string
  onOpenTransactions: (accountId: string, dates?: AccountReviewDates) => void
}) {
  const [offset, setOffset] = useState(0),
    [showAll, setShowAll] = useState(false)
  const [search, setSearch] = useState(""),
    [appliedSearch, setAppliedSearch] = useState("")
  const [payments, setPayments] = useState<Reference | null>(null),
    [finding, setFinding] = useState<Reference | null>(null)
  const [source, setSource] = useState<string | null>(null),
    [account, setAccount] = useState<
      Reference["possible_accounts"][number] | null
    >(null)
  const { canEdit } = useFinancialAccess()
  const query = useQuery({
    queryKey: [
      "financial-account-references",
      caseId,
      offset,
      showAll,
      appliedSearch,
    ],
    retry: false,
    queryFn: async ({ signal }) => {
      const params = new URLSearchParams({
        case_id: caseId,
        offset: String(offset),
        show: showAll ? "all" : "missing",
        search: appliedSearch,
      })
      const data = response.parse(
        await fetchAPI(`/api/financial/account-references?${params}`, {
          signal,
        })
      )
      if (data.case_id !== caseId || data.offset !== offset)
        throw Error(
          "The account references did not match this case. Refresh the list."
        )
      return data
    },
  })
  return (
    <section
      aria-label="Account references in payments"
      className="finance-panel rounded-xl border p-4 space-y-4"
      data-finance-tone="review"
    >
      <div className="flex flex-wrap justify-between gap-3">
        <div>
          <h2 className="flex gap-2 items-center font-semibold">
            <Landmark className="h-4 w-4" />
            Other accounts mentioned in payments
          </h2>
          <p className="text-sm text-muted-foreground mt-1">
            Follow account, card, share and IBAN references printed in payment
            descriptions. Check the original before requesting more statements.
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          disabled={query.isFetching}
          onClick={() => void query.refetch()}
        >
          <RefreshCw className="h-4 w-4" />
          Refresh references
        </Button>
      </div>
      <form
        className="flex flex-wrap gap-3 items-end"
        onSubmit={(event) => {
          event.preventDefault()
          setOffset(0)
          setAppliedSearch(search.trim())
        }}
      >
        <label className="text-sm">
          Find a reference
          <input
            aria-label="Find an account reference"
            value={search}
            maxLength={128}
            onChange={(event) => setSearch(event.target.value)}
            className="block rounded border bg-background p-2 mt-1"
          />
        </label>
        <Button type="submit" variant="outline" size="sm">
          Search references
        </Button>
        <label className="text-sm flex items-center gap-2">
          <input
            type="checkbox"
            checked={showAll}
            onChange={(event) => {
              setShowAll(event.target.checked)
              setOffset(0)
            }}
          />
          Include references with a possible statement match
        </label>
      </form>
      {query.isFetching && (
        <p role="status">Checking account references in imported payments…</p>
      )}
      {query.isError && (
        <p role="alert">
          {query.error.message} Use Refresh references to retry.
        </p>
      )}
      {query.data && !query.isFetching && !query.isError && (
        <>
          <p className="text-sm">
            {query.data.missing_count} references without a matching imported
            statement · {query.data.possible_match_count} with a possible match
            · {query.data.scanned_payments.toLocaleString()} payments checked
          </p>
          {!query.data.items.length && (
            <p className="text-sm">
              {appliedSearch || offset
                ? "No references match this page or search. Clear the search or return to the previous page."
                : "No unmatched labelled account references were found in these payments. Accounts mentioned without a readable reference will need to be checked in the originals."}
            </p>
          )}
          <div className="space-y-3">
            {query.data.items.map((item) => (
              <article
                key={item.id}
                className="rounded-lg border bg-card p-3 space-y-3"
              >
                <div className="flex flex-wrap justify-between gap-2">
                  <div>
                    <h3 className="font-semibold">
                      {item.kind === "share"
                        ? "Share "
                        : item.kind === "iban"
                          ? "IBAN "
                          : "Account reference "}
                      {item.reference}
                    </h3>
                    <p className="text-sm text-muted-foreground">
                      {item.payment_count.toLocaleString()} payments ·{" "}
                      {item.partial
                        ? "Partial reference, check the account holder"
                        : "Account holder not established from this reference"}
                    </p>
                  </div>
                  <span className="text-sm font-medium">
                    {item.status === "no_statement_found"
                      ? "No matching statement imported"
                      : "Possible statement match"}
                  </span>
                </div>
                {item.examples.slice(0, 1).map((example) => (
                  <p className="text-sm break-words" key={example.payment_id}>
                    {example.text.slice(0, example.start)}
                    <mark className="rounded bg-amber-100 dark:bg-amber-900 text-foreground px-0.5">
                      {example.text.slice(example.start, example.end)}
                    </mark>
                    {example.text.slice(example.end)}
                  </p>
                ))}
                <div className="flex flex-wrap gap-2">
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => setPayments(item)}
                  >
                    View {item.payment_count} payments
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() =>
                      setSource(
                        item.examples[0]?.payment_id ?? item.payment_ids[0]
                      )
                    }
                  >
                    View original statement
                  </Button>
                  <Button
                    size="sm"
                    disabled={!canEdit}
                    onClick={() => setFinding(item)}
                  >
                    Save question in Findings
                  </Button>
                </div>
                {!!item.possible_accounts.length && (
                  <div className="text-sm space-y-2">
                    <p>
                      Compare these recorded accounts. A matching number or card
                      ending alone does not confirm the account holder.
                    </p>
                    {item.possible_accounts.map((other) => (
                      <Button
                        key={other.account_id}
                        size="sm"
                        variant="outline"
                        onClick={() => setAccount(other)}
                      >
                        {other.holder || other.reference} ·{" "}
                        {other.bank || "Bank not recorded"} ·{" "}
                        {other.statement_count} statements
                      </Button>
                    ))}
                  </div>
                )}
              </article>
            ))}
          </div>
          <div className="flex items-center gap-3">
            <Button
              size="sm"
              variant="outline"
              disabled={!offset}
              onClick={() => setOffset(Math.max(0, offset - 25))}
            >
              Previous references
            </Button>
            <span className="text-sm">
              {query.data.total ? offset + 1 : 0}–
              {Math.min(offset + 25, query.data.total)} of {query.data.total}
            </span>
            <Button
              size="sm"
              variant="outline"
              disabled={offset + 25 >= query.data.total}
              onClick={() => setOffset(offset + 25)}
            >
              Next references
            </Button>
          </div>
        </>
      )}
      {payments && (
        <SelectedPaymentsReview
          caseId={caseId}
          ids={payments.payment_ids}
          onClose={() => setPayments(null)}
        />
      )}
      {source && (
        <LedgerSourceDialog
          caseId={caseId}
          transactionId={source}
          onClose={() => {
            setSource(null)
            void query.refetch()
          }}
        />
      )}
      {finding && (
        <InvestigatorFindingEditor
          caseId={caseId}
          ids={finding.payment_ids}
          initial={{
            kind: "question",
            title: `Which account is ${finding.reference}?`,
            explanation: `${finding.payment_count} imported payments mention ${finding.variants.join(" / ")}. ${finding.status === "no_statement_found" ? "No matching imported statement was found in this case when this question was created." : "Possible matching statements need comparison."} ${finding.partial ? "The printed reference is incomplete." : "The account holder has not been established from the reference."}`,
            nextAction:
              "Check the cited original payments, establish the account holder and bank, and request the relevant statements if needed.",
          }}
          onClose={() => setFinding(null)}
        />
      )}
      {account && (
        <Dialog
          open
          onOpenChange={(open) => {
            if (!open) setAccount(null)
          }}
        >
          <DialogContent className="sm:max-w-5xl max-h-[90vh] overflow-auto">
            <DialogHeader>
              <DialogTitle>Compare this account's statements</DialogTitle>
              <DialogDescription>
                Check the original files before deciding that the payment refers
                to this account.
              </DialogDescription>
            </DialogHeader>
            <AccountStatementReview
              caseId={caseId}
              account={{
                id: account.account_id,
                holder: account.holder,
                identifier: account.reference,
                institution: account.bank,
                currency: null,
              }}
              onBack={() => setAccount(null)}
              onOpenTransactions={(dates) => {
                onOpenTransactions(account.account_id, dates)
                setAccount(null)
              }}
              datesFirst
            />
          </DialogContent>
        </Dialog>
      )}
    </section>
  )
}
