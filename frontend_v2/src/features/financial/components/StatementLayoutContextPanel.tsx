import { useState } from "react"
import { Button } from "@/components/ui/button"
import type {
  StatementLayoutContext,
  LayoutCitation,
} from "../lib/statement-layout-context"
export function StatementLayoutContextPanel({
  context,
  onSource,
}: {
  context: StatementLayoutContext
  onSource: (cell: LayoutCitation) => void
}) {
  const [open, setOpen] = useState(false),
    [page, setPage] = useState(0)
  return (
    <div className="space-y-2">
      <Button variant="outline" onClick={() => setOpen((v) => !v)}>
        {open
          ? "Hide printed statement context"
          : "Inspect printed statement context"}
      </Button>
      {open && (
        <section
          aria-label="Printed statement layout context"
          className="space-y-3 rounded border p-3"
        >
          <h4 className="font-semibold">
            Printed card sections and possible transaction dates
          </h4>
          <p>{context.limitation}</p>
          <p>
            Printed cycle: {context.start_date} to {context.end_date}. Layout:{" "}
            {context.layout_id}, version {context.version}.
          </p>
          <div className="flex flex-wrap gap-2">
            <Button
              variant="outline"
              onClick={() => onSource(context.cycle_source)}
            >
              Inspect printed billing cycle
            </Button>
            {context.cycle_count_source && (
              <Button
                variant="outline"
                onClick={() => onSource(context.cycle_count_source!)}
              >
                Inspect printed cycle day count
              </Button>
            )}
            <Button
              variant="outline"
              onClick={() => onSource(context.printed_card_source)}
            >
              Inspect printed card heading
            </Button>
          </div>
          {!context.rows.length && (
            <p>
              No rows matched the supported section layout. Inspect the original
              manually.
            </p>
          )}
          {context.rows.slice(page * 10, page * 10 + 10).map((row) => (
            <div key={row.row_index} className="space-y-2 border-t pt-2">
              <p>
                Row {row.row_index + 1}: printed card ending {row.card_ending} ·{" "}
                {row.printed_section}
              </p>
              <p>
                Source{" "}
                {row.date_label === "Trans Date" ? "transaction date" : "date"}:{" "}
                {row.date_source.expected_text}.{" "}
                {row.date_proposals.length
                  ? `Possible date within this cycle: ${row.date_proposals.join(" or ")}. Confirm against the original.`
                  : "No supported date falls within the printed cycle; date remains unresolved."}
              </p>
              {row.posting_date_source && (
                <p>
                  Source posting date: {row.posting_date_source.expected_text}.{" "}
                  {row.posting_date_proposals.length
                    ? `Possible posting date within this cycle: ${row.posting_date_proposals.join(" or ")}. Confirm separately from the transaction date.`
                    : "No supported posting date falls within this cycle; it remains unresolved."}
                </p>
              )}
              <p>
                Description: {row.description_source.expected_text} · Amount
                text: {row.amount_source.expected_text}. This layout aid does
                not determine money direction.
              </p>
              <div className="flex flex-wrap gap-2">
                <Button
                  variant="outline"
                  onClick={() => onSource(row.section_source)}
                >
                  Inspect section for row {row.row_index + 1}
                </Button>
                <Button
                  variant="outline"
                  onClick={() => onSource(row.date_source)}
                >
                  Inspect date for row {row.row_index + 1}
                </Button>
                <Button
                  variant="outline"
                  onClick={() => onSource(row.amount_source)}
                >
                  Inspect amount for row {row.row_index + 1}
                </Button>
                {row.posting_date_source && (
                  <Button
                    variant="outline"
                    onClick={() => onSource(row.posting_date_source!)}
                  >
                    Inspect posting date for row {row.row_index + 1}
                  </Button>
                )}
                {row.date_header_source && (
                  <Button
                    variant="outline"
                    onClick={() => onSource(row.date_header_source!)}
                  >
                    Inspect date heading for row {row.row_index + 1}
                  </Button>
                )}
              </div>
            </div>
          ))}
          {context.rows.length > 10 && (
            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                disabled={!page}
                onClick={() => setPage((p) => p - 1)}
              >
                Previous context rows
              </Button>
              <span>
                Page {page + 1} of {Math.ceil(context.rows.length / 10)}
              </span>
              <Button
                variant="outline"
                disabled={(page + 1) * 10 >= context.rows.length}
                onClick={() => setPage((p) => p + 1)}
              >
                Next context rows
              </Button>
            </div>
          )}
        </section>
      )}
    </div>
  )
}
