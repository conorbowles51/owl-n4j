import { PaymentCounterpartyPicker } from "./PaymentCounterpartyPicker"
import { Button } from "@/components/ui/button"
import type { StatementDraft } from "../lib/statement-review-draft"

type Edit = StatementDraft["rows"][number]
export function StatementRowEditor({
  row,
  caseId,
  kind,
  statementEnd,
  additionalPrintedDate,
  problems,
  update,
  amount,
  balance,
  text,
  close,
}: {
  row: Edit
  caseId: string
  kind: string
  statementEnd?: string
  additionalPrintedDate?: string
  problems: string[]
  update: (patch: Partial<Edit>) => void
  amount: (direction: "credit" | "debit", value: string) => void
  balance: (value: string) => void
  text: (field: "credit" | "debit" | "balance") => string
  close: () => void
}) {
  const control = kind === "balance" || kind === "statement_total"
  const fieldClass =
    "mt-1 block w-full rounded border bg-background p-2 text-sm"
  return (
    <section
      aria-label="Edit selected statement row"
      className="rounded border border-primary/30 bg-background p-3 space-y-3 text-sm font-sans"
    >
      <div className="flex flex-wrap justify-between items-center gap-2">
        <h5 className="font-semibold">Correct this reading</h5>
        <Button size="sm" variant="outline" onClick={close}>
          Done editing this row
        </Button>
      </div>
      <p className="text-muted-foreground">
        The printed row above is retained. Your corrected values will be used
        for the import.
      </p>
      {!control && (
        <label className="flex items-center gap-2">
          <input
            type="checkbox"
            checked={!row.excluded}
            onChange={(event) => update({ excluded: !event.target.checked })}
          />
          Include this transaction
        </label>
      )}
      {!control && (
        <div className="grid gap-3 sm:grid-cols-2">
          <label>
            Transaction date
            {additionalPrintedDate && (
              <span className="block text-xs text-muted-foreground">
                Uses the first date on the printed row. The additional date{" "}
                {additionalPrintedDate} is retained in the original; its meaning
                is not labelled.
              </span>
            )}
            {row.date_unprinted && (
              <span className="block text-xs text-muted-foreground">
                Date not printed. This interest charge belongs to the statement
                ending {statementEnd || "on the date entered below"}. Leave the
                date blank unless you find a date in the source.
              </span>
            )}
            <input
              aria-label="Corrected transaction date"
              type="date"
              className={fieldClass}
              value={row.date}
              disabled={row.excluded}
              onChange={(event) => update({ date: event.target.value })}
            />
          </label>
          {Object.entries(row.date_values || {}).map(([role, value]) => (
            <label key={role}>
              {role === "booking_date"
                ? "Posting date"
                : role === "value_date"
                  ? "Value date"
                  : "Additional date"}
              <input
                type="date"
                className={fieldClass}
                value={value}
                disabled={row.excluded}
                onChange={(event) =>
                  update({
                    date_values: {
                      ...row.date_values,
                      [role]: event.target.value,
                    },
                  })
                }
              />
            </label>
          ))}
          <label className="sm:col-span-2">
            Description
            <input
              aria-label="Corrected description"
              className={fieldClass}
              value={row.description}
              disabled={row.excluded}
              onChange={(event) => update({ description: event.target.value })}
            />
          </label>
          {(["credit", "debit"] as const).map((direction) => (
            <label key={direction}>
              {direction === "credit"
                ? "Credit / money in"
                : "Debit / money out"}
              <input
                aria-label={`Corrected ${direction}`}
                className={fieldClass}
                inputMode="decimal"
                value={text(direction)}
                disabled={
                  row.excluded ||
                  (!!row.amount_minor &&
                    row.amount_minor !== "0" &&
                    !!row.direction &&
                    row.direction !== direction)
                }
                onChange={(event) => amount(direction, event.target.value)}
              />
              {!row.excluded &&
                row.direction &&
                row.direction !== direction &&
                row.amount_minor &&
                row.amount_minor !== "0" && (
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => update({ direction })}
                  >
                    Move amount to{" "}
                    {direction === "credit"
                      ? "Credit / money in"
                      : "Debit / money out"}
                  </Button>
                )}
            </label>
          ))}
          <label className="sm:col-span-2">
            Paid by / paid to
            <input
              aria-label="Corrected paid by or paid to"
              className={fieldClass}
              value={row.counterparty}
              disabled={row.excluded}
              onChange={(event) => update({ counterparty: event.target.value })}
            />
          </label>
          <PaymentCounterpartyPicker
            caseId={caseId}
            value={row.counterparty_link}
            direction={row.direction}
            disabled={row.excluded}
            onChange={(link) => update({ counterparty_link: link })}
          />
        </div>
      )}
      <label className="block">
        {kind === "statement_total" ? "Printed total" : "Printed balance"}
        <input
          aria-label={
            kind === "statement_total"
              ? "Corrected printed total"
              : "Corrected printed balance"
          }
          className={fieldClass}
          inputMode="decimal"
          value={text("balance")}
          onChange={(event) => balance(event.target.value)}
        />
      </label>
      <label className="block">
        Note about this change (optional)
        <input
          aria-label="Reason for this row correction"
          className={fieldClass}
          value={row.reason}
          onChange={(event) => update({ reason: event.target.value })}
        />
      </label>
      {problems.length > 0 && (
        <ul className="list-disc pl-5 text-amber-800 dark:text-amber-200">
          {problems.map((problem) => (
            <li key={problem}>{problem}</li>
          ))}
        </ul>
      )}
    </section>
  )
}
