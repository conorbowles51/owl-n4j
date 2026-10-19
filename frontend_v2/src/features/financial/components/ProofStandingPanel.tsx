import { Button } from "@/components/ui/button"
import { useProofStanding } from "../hooks/use-proof-standing"
import { readProofClass } from "../lib/ledger-format"

const number = (value: number) => value.toLocaleString("en-US")

/** A census of class, not a count of outstanding reviews or currently admitted rows. */
export function ProofStandingPanel({ caseId }: { caseId: string | undefined }) {
  const { data, isPending, isError, error, isFetching, refetch } =
    useProofStanding(caseId)
  return (
    <section
      aria-label="Evidence classification"
      className="space-y-3 rounded-lg border bg-card p-4"
      data-testid="proof-standing-panel"
    >
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-sm font-semibold">Evidence classification</h2>
        {caseId && (
          <Button
            variant="outline"
            size="sm"
            disabled={isFetching}
            onClick={() => void refetch()}
          >
            Refresh classification
          </Button>
        )}
      </div>
      {!caseId ? (
        <p className="text-sm text-muted-foreground">
          Choose a case to see its evidence classification.
        </p>
      ) : isPending ? (
        <p role="status" className="text-sm text-muted-foreground">
          Reading evidence classification...
        </p>
      ) : isError ? (
        <p role="alert" className="text-sm text-destructive">
          Evidence classification could not be read. No counts are shown.{" "}
          {error instanceof Error ? error.message : ""}
        </p>
      ) : (
        data && (
          <>
            {isFetching && (
              <p role="status" className="text-xs text-muted-foreground">
                Refreshing classification; showing the last successful reading.
              </p>
            )}
            <p className="text-sm" data-testid="proof-standing-totals">
              {number(data.documents)} financial source documents ·{" "}
              {number(data.transactions)} ledger rows
            </p>
            {data.documents === 0 && data.transactions === 0 && (
              <p className="text-sm text-muted-foreground">
                No financial source documents or ledger rows have been recorded
                here. This does not mean the case has no financial evidence.
              </p>
            )}
            <p className="text-sm" data-testid="proof-standing-human-decision">
              In classes requiring a recorded human decision:{" "}
              {number(data.documents_requiring_adjudication)} documents and{" "}
              {number(data.transactions_requiring_adjudication)} rows.
            </p>
            <p className="text-xs text-muted-foreground">
              These counts include held-out, superseded and rejected records.
              They describe evidence classes, not reviews still waiting for a
              decision or rows currently included in totals.
            </p>
            <details>
              <summary className="cursor-pointer text-sm font-medium">
                View all classes and their rules
              </summary>
              <div className="mt-3 overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <caption className="mb-2 text-left text-muted-foreground">
                    Rules reported for this case. A class is computed from its
                    source and verification results; it cannot be set here.
                  </caption>
                  <thead>
                    <tr className="border-b">
                      <th scope="col" className="p-2">
                        Evidence class
                      </th>
                      <th scope="col" className="p-2 text-right">
                        Documents
                      </th>
                      <th scope="col" className="p-2 text-right">
                        Rows
                      </th>
                      <th scope="col" className="p-2">
                        Automatic admission
                      </th>
                      <th scope="col" className="p-2">
                        Human decision required
                      </th>
                      <th scope="col" className="p-2">
                        May produce ledger rows
                      </th>
                      <th scope="col" className="p-2">
                        Class eligible for totals
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.classes.map((row) => {
                      const term = readProofClass(row.proof_class)
                      return (
                        <tr
                          key={row.proof_class}
                          className="border-b last:border-0"
                        >
                          <th
                            scope="row"
                            className="max-w-72 p-2 align-top font-normal"
                          >
                            <span
                              className={
                                term.value === null
                                  ? "font-semibold text-amber-700 dark:text-amber-400"
                                  : "font-semibold"
                              }
                            >
                              {term.label}
                            </span>
                            <p className="mt-1 text-muted-foreground">
                              {term.description}
                            </p>
                          </th>
                          <td className="p-2 text-right align-top tabular-nums">
                            {number(row.documents)}
                          </td>
                          <td className="p-2 text-right align-top tabular-nums">
                            {number(row.transactions)}
                          </td>
                          <td className="p-2 align-top">
                            {row.admits_automatically ? "Yes" : "No"}
                          </td>
                          <td className="p-2 align-top">
                            {row.requires_adjudication ? "Yes" : "No"}
                          </td>
                          <td className="p-2 align-top">
                            {row.may_produce_ledger_rows ? "Yes" : "No"}
                          </td>
                          <td className="p-2 align-top">
                            {row.counts_toward_totals ? "Yes" : "No"}
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
              <p className="mt-3 text-xs text-muted-foreground">
                Classes eligible for totals:{" "}
                {data.counted_classes.length
                  ? data.counted_classes
                      .map((value) => readProofClass(value).label)
                      .join(", ")
                  : "none"}
                . Eligibility does not mean every row in that class is counted.
                Held-out, superseded and rejected rows remain excluded.
              </p>
            </details>
          </>
        )
      )}
    </section>
  )
}
