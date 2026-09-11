import {
  AccountStatementReview,
  type AccountReviewDates,
} from "./AccountStatementReview"
import type { z } from "zod"
import { useRef, useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { Button } from "@/components/ui/button"
import { fetchAPI } from "@/lib/api-client"
import {
  candidateAccounts,
  candidateUrl,
  assertCandidateScope,
} from "../lib/candidate-contract"

export function FinancialAccounts({
  caseId,
  onOpenAccount,
}: {
  caseId: string | undefined
  onOpenAccount: (accountId: string, dates?: AccountReviewDates) => void
}) {
  const [reviewAccount, setReviewAccount] = useState<
    z.infer<typeof candidateAccounts>["items"][number] | null
  >(null)
  const [reviewOpen, setReviewOpen] = useState(false)
  const root = useRef<HTMLElement>(null)
  const showReview = () => {
    setReviewOpen(true)
    root.current?.scrollIntoView?.({ block: "start" })
  }
  const [draftSearch, setDraftSearch] = useState("")
  const [search, setSearch] = useState("")
  const query = useQuery({
    queryKey: ["financial-ledger", caseId, "filter-accounts", search],
    enabled: !!caseId,
    retry: false,
    queryFn: async () => {
      const result = candidateAccounts.parse(
        await fetchAPI(
          `${candidateUrl("ledger-accounts", caseId!)}&${new URLSearchParams({ search })}`
        )
      )
      assertCandidateScope(result, caseId!)
      return result
    },
  })
  if (!caseId) return null
  return (
    <section
      aria-label="Financial accounts"
      ref={root}
      className="space-y-3 rounded border p-4"
    >
      {reviewAccount && (
        <div hidden={!reviewOpen}>
          <AccountStatementReview
            key={reviewAccount.id}
            caseId={caseId}
            account={reviewAccount}
            onBack={() => setReviewOpen(false)}
            onOpenTransactions={(dates) =>
              onOpenAccount(reviewAccount.id, dates)
            }
          />
        </div>
      )}
      <div hidden={reviewOpen} className="space-y-3">
        <h3 className="font-semibold">Accounts in this case</h3>
        <p className="text-sm text-muted-foreground">
          Review an account’s statements, balances and missing dates, or open
          its transactions.
        </p>
        <form
          className="flex flex-wrap gap-2"
          onSubmit={(event) => {
            event.preventDefault()
            setSearch(draftSearch.trim())
          }}
        >
          <label className="flex-1 min-w-56 text-sm">
            Find an account
            <input
              aria-label="Search financial accounts"
              maxLength={128}
              className="block w-full rounded border bg-background p-2"
              placeholder="Holder, account number or bank"
              value={draftSearch}
              onChange={(event) => setDraftSearch(event.target.value)}
            />
          </label>
          <Button type="submit" className="self-end">
            Find accounts
          </Button>
          <Button
            type="button"
            variant="outline"
            className="self-end"
            onClick={() => {
              setDraftSearch("")
              setSearch("")
            }}
          >
            Show all accounts
          </Button>
        </form>
        {query.isPending ? (
          <p role="status">Loading accounts…</p>
        ) : query.isError ? (
          <div role="alert">
            <p>Accounts could not be loaded. {query.error.message}</p>
            <Button onClick={() => void query.refetch()}>Retry accounts</Button>
          </div>
        ) : (
          <>
            {query.data.items.length === 0 && (
              <p>
                {search
                  ? "No account matches this search. Try part of the holder's name or account number."
                  : "No financial accounts have been recorded yet. Import a statement here to add its account and payments."}
              </p>
            )}
            <div className="grid gap-3 lg:grid-cols-2">
              {query.data.items.map((account) => (
                <article
                  key={account.id}
                  className="rounded border p-4 space-y-2"
                >
                  <h4 className="font-semibold">
                    {account.holder || "Account holder not recorded"}
                  </h4>
                  <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
                    <dt className="text-muted-foreground">Account number</dt>
                    <dd className="break-all font-mono">
                      {account.identifier || "Not recorded"}
                    </dd>
                    <dt className="text-muted-foreground">Bank</dt>
                    <dd>{account.institution || "Not recorded"}</dd>
                    <dt className="text-muted-foreground">Currency</dt>
                    <dd>{account.currency || "Not recorded"}</dd>
                  </dl>
                  {account.provisional && (
                    <p className="text-sm">
                      Account identity still needs review.
                    </p>
                  )}
                  <div className="flex flex-wrap gap-2">
                    <Button
                      onClick={() => {
                        setReviewAccount(account)
                        showReview()
                      }}
                    >
                      Review statements
                    </Button>
                    <Button
                      variant="outline"
                      onClick={() => onOpenAccount(account.id)}
                    >
                      View all transactions
                    </Button>
                  </div>
                </article>
              ))}
            </div>
            {query.data.has_more && (
              <p role="status">
                More accounts match than can be shown here. Search by holder,
                number or bank to narrow the list.
              </p>
            )}
          </>
        )}
      </div>
    </section>
  )
}
