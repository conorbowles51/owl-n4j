/**
 * The column mapping of a spreadsheet statement, shown before it is stored.
 *
 * A bank or payment-app export is a table with no format of its own, so the
 * reader guesses which column is the date, the money and the balance. This
 * panel shows that guess (or the mapping a person confirmed for the same
 * headings earlier in the case) and lets the person change it. Storing the
 * file confirms the mapping shown; a changed mapping must be read again first,
 * so what is stored is always what was seen.
 */
import { SPREADSHEET_ROLES, type SpreadsheetLayout, type SpreadsheetRole } from "../api"
import { ROLE_LABELS, roleOfColumn, withColumnRole } from "../lib/spreadsheet-layout"

function confirmedLine(layout: SpreadsheetLayout): string {
  if (layout.source !== "confirmed") {
    return "The reader guessed this mapping from the headings. Check it: adding the file to the ledger confirms it for every file with these headings in this case."
  }
  const who = layout.confirmed_by?.name || layout.confirmed_by?.email
  const when = layout.confirmed_at ? new Date(layout.confirmed_at).toLocaleDateString() : null
  if (who && when) return `Confirmed by ${who} on ${when} for files with these headings.`
  if (who) return `Confirmed by ${who} for files with these headings.`
  return "Confirmed for files with these headings."
}

export function SpreadsheetMapping({
  layouts,
  onChange,
  disabled,
}: {
  layouts: SpreadsheetLayout[]
  onChange: (next: SpreadsheetLayout[]) => void
  disabled: boolean
}) {
  const update = (index: number, next: SpreadsheetLayout) =>
    onChange(layouts.map((layout, i) => (i === index ? next : layout)))

  return (
    <div className="space-y-3" data-testid="spreadsheet-mapping">
      {layouts.map((layout, index) => (
        <div
          key={`${layout.sheet ?? ""}:${layout.layout_key}`}
          className="space-y-2 rounded-md border border-border/70 p-3"
        >
          <p className="text-xs font-medium">
            {layout.sheet ? `Sheet "${layout.sheet}", ` : ""}headings on line {layout.header_line}
          </p>
          <p className="text-xs text-muted-foreground" data-testid="mapping-source">
            {confirmedLine(layout)}
          </p>
          <div className="grid grid-cols-2 gap-x-3 gap-y-1.5">
            {layout.headings.map((heading, column) =>
              heading ? (
                <label key={column} className="contents text-xs">
                  <span className="truncate py-1" title={heading}>
                    {heading}
                  </span>
                  <select
                    className="rounded border border-border bg-background px-1 py-0.5 text-xs"
                    data-testid={`mapping-column-${column}`}
                    disabled={disabled}
                    value={roleOfColumn(layout, column) ?? ""}
                    onChange={(e) =>
                      update(
                        index,
                        withColumnRole(layout, column, (e.target.value || null) as SpreadsheetRole | null)
                      )
                    }
                  >
                    <option value="">Not used</option>
                    {SPREADSHEET_ROLES.map((role) => (
                      <option key={role} value={role}>
                        {ROLE_LABELS[role]}
                      </option>
                    ))}
                  </select>
                </label>
              ) : null
            )}
          </div>
          {layout.columns.amount != null && (
            <label className="flex items-center gap-2 text-xs">
              <span>A minus sign in the amount means</span>
              <select
                className="rounded border border-border bg-background px-1 py-0.5 text-xs"
                data-testid="mapping-sign"
                disabled={disabled}
                value={layout.amount_sign}
                onChange={(e) =>
                  update(index, {
                    ...layout,
                    amount_sign: e.target.value as SpreadsheetLayout["amount_sign"],
                  })
                }
              >
                <option value="negative_is_out">money out of the account</option>
                <option value="negative_is_in">money into the account</option>
              </select>
            </label>
          )}
          {layout.date_order_source === "file" ? (
            <p className="text-xs text-muted-foreground">
              The file's own dates show they are written{" "}
              {layout.date_order_used === "day_first" ? "day first" : "month first"}.
            </p>
          ) : (
            <label className="flex items-center gap-2 text-xs">
              <span>Dates like 03/04 are</span>
              <select
                className="rounded border border-border bg-background px-1 py-0.5 text-xs"
                data-testid="mapping-date-order"
                disabled={disabled}
                value={layout.date_order ?? ""}
                onChange={(e) =>
                  update(index, {
                    ...layout,
                    date_order: (e.target.value || null) as SpreadsheetLayout["date_order"],
                  })
                }
              >
                <option value="">not decided (listed as unsure)</option>
                <option value="month_first">month first (3 April is 04/03)</option>
                <option value="day_first">day first (3 April is 03/04)</option>
              </select>
            </label>
          )}
        </div>
      ))}
    </div>
  )
}

/** Lines the reader skipped, every one counted; the list shows the first ones and says how many more. */
export function SkippedLines({
  skipped,
  unsure,
  shown = 20,
}: {
  skipped: { row_index: number; reason: string }[]
  unsure: number
  shown?: number
}) {
  if (skipped.length === 0) return null
  return (
    <div className="space-y-1" data-testid="skipped-lines">
      <p className="text-xs font-medium">
        {skipped.length} line{skipped.length === 1 ? "" : "s"} not added
        {unsure > 0 && `, ${unsure} of them unsure`}:
      </p>
      <ul className="list-disc space-y-0.5 pl-4 text-xs text-muted-foreground">
        {skipped.slice(0, shown).map((row) => (
          <li key={row.row_index}>{row.reason}</li>
        ))}
      </ul>
      {skipped.length > shown && (
        <p className="text-xs text-muted-foreground">
          Showing {shown} of {skipped.length}.
        </p>
      )}
    </div>
  )
}
