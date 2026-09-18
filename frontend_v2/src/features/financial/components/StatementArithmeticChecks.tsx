import { z } from "zod"
import { Button } from "@/components/ui/button"
import { arithmeticCheck } from "../hooks/use-statement-checks"

const names = {
  closing_balance: "Opening and closing balance",
  running_balance: "Balances between payments",
  credit_total: "Printed money-in total",
  debit_total: "Printed money-out total",
  fee_total: "Fees against printed total",
  interest_total: "Interest charges against printed total",
}
export function StatementArithmeticChecks({
  checks,
  format,
  onInspect,
}: {
  checks: z.infer<typeof arithmeticCheck>[]
  format: (value: string) => string
  onInspect: (id: string) => void
}) {
  const available = checks.filter((check) => check.status !== "unavailable")
  const unavailable = checks.filter((check) => check.status === "unavailable")
  return (
    <div className="space-y-2">
      {available.map((check) => (
        <div
          key={check.kind}
          className={`rounded border p-3 ${check.status === "difference" ? "border-amber-500/50 bg-amber-50/50 dark:bg-amber-950/20" : "border-teal-500/30 bg-teal-50/40 dark:bg-teal-950/10"}`}
        >
          <p className="font-medium">
            {names[check.kind]}:{" "}
            {check.status === "matches" ? "matches" : "needs checking"}
          </p>
          {check.kind === "running_balance" ? (
            <>
              <p>
                {check.compared_intervals} balance intervals checked.{" "}
                {check.mismatch_count} differences found.
              </p>
              {check.findings?.map((item, index) => (
                <div
                  key={index}
                  className="flex flex-wrap items-center gap-2 mt-2"
                >
                  <span>
                    Page {item.page}: payments give{" "}
                    {format(item.expected_minor)}; printed balance{" "}
                    {format(item.printed_minor)}.
                  </span>
                  {item.row_id && (
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => onInspect(item.row_id!)}
                    >
                      Check this balance
                    </Button>
                  )}
                </div>
              ))}
              {check.findings_truncated && (
                <p>
                  The first 100 differences are shown. All intervals were
                  checked. Correct these, then the checks will run again.
                </p>
              )}
            </>
          ) : (
            <div className="flex flex-wrap items-center gap-2">
              <span>
                Calculated {format(check.expected_minor!)}. Printed{" "}
                {format(check.printed_minor!)}.
                {check.status === "difference" &&
                  ` Difference ${format(check.difference_minor!)}.`}
              </span>
              {check.row_id && (
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => onInspect(check.row_id!)}
                >
                  View printed value
                </Button>
              )}
              {check.status === "difference" &&
                check.contributing_row_ids?.map((id, index) => (
                  <Button
                    key={id}
                    size="sm"
                    variant="outline"
                    onClick={() => onInspect(id)}
                  >
                    Check charge {index + 1}
                  </Button>
                ))}
            </div>
          )}
        </div>
      ))}
      {unavailable.length > 0 && (
        <details className="text-muted-foreground">
          <summary className="cursor-pointer">
            {unavailable.length} checks unavailable
          </summary>
          <ul className="list-disc pl-5 mt-2">
            {unavailable.map((check) => (
              <li key={check.kind}>
                {names[check.kind]}: {check.reason}
              </li>
            ))}
          </ul>
          <p className="mt-2">
            A missing printed total does not prevent import. You can compare the
            transactions with the PDF.
          </p>
        </details>
      )}
    </div>
  )
}
