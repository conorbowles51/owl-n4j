import { Fragment, type ReactNode } from "react"
import { Button } from "@/components/ui/button"
import {
  printedStatementSections,
  type PrintedCell,
  type PrintedRow,
} from "../lib/printed-statement-sections"

export function PrintedStatementTable({
  rows,
  onCell,
  onReviewRow,
  selectedRowId,
  rowTools,
}: {
  rows: PrintedRow[]
  selectedRowId?: string
  onCell: (rowId: string, locator: unknown) => void
  onReviewRow?: (rowId: string) => void
  rowTools?: (rowId: string) => ReactNode
}) {
  const positioned = rows.filter(
    (row) => row.fields?.statement_layout === "andrews-share-statement"
  )
  const { sections, remaining } = printedStatementSections(
    rows.filter((row) => !positioned.includes(row))
  )
  const cell = (id: string, value: PrintedCell | undefined) =>
    value?.expected_text ? (
      <button
        type="button"
        className="text-left whitespace-pre-wrap hover:bg-accent focus-visible:outline-2 focus-visible:outline-primary"
        onClick={() => onCell(id, value.locator)}
      >
        {value.expected_text}
      </button>
    ) : null
  const unresolved = remaining.filter(
    (row) =>
      row.kind === "transaction" ||
      row.kind === "unresolved" ||
      !!row.issues?.length
  )
  const additional = remaining.filter((row) => !unresolved.includes(row))
  return (
    <div className="space-y-4">
      {positioned.length > 0 && (
        <PositionedStatementRows
          rows={positioned}
          onCell={onCell}
          selectedRowId={selectedRowId}
          rowTools={rowTools}
        />
      )}
      {sections.map((section) => (
        <section key={section.key} className="space-y-2">
          {section.title && (
            <h5 className="font-semibold text-sm">
              {cell(section.titleRowId, section.title)}
            </h5>
          )}
          <div className="overflow-auto">
            <table
              className="w-full border-collapse text-sm"
              aria-label={`Extracted printed table, page ${section.page}, section ${section.key}`}
            >
              {section.headers.length > 0 && (
                <thead className="bg-muted/40">
                  <tr>
                    {section.columns.map(({ header }, index) => (
                      <th
                        key={index}
                        className="border p-2 text-left"
                        aria-label={
                          header ? undefined : "Unlabelled printed column"
                        }
                      >
                        {header && cell(section.key, header)}
                      </th>
                    ))}
                  </tr>
                </thead>
              )}
              <tbody>
                {section.rows.map(({ row, cells, parts }) => (
                  <Fragment key={row.id}>
                    <tr
                      key={row.id}
                      data-statement-row={row.id}
                      className={
                        row.id === selectedRowId
                          ? "bg-amber-100/70 dark:bg-amber-900/30"
                          : undefined
                      }
                    >
                      {cells.map((value, index) => (
                        <td key={index} className="border p-2 align-top">
                          {(parts?.[index] ?? (value ? [value] : [])).map(
                            (part, partIndex) => (
                              <Fragment key={part.column_index}>
                                {partIndex > 0 ? " " : null}
                                {cell(row.id, part)}
                              </Fragment>
                            )
                          )}
                        </td>
                      ))}
                    </tr>
                    {rowTools?.(row.id) && (
                      <tr>
                        <td
                          colSpan={section.columns.length}
                          className="border p-2"
                        >
                          {rowTools(row.id)}
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ))}
      {unresolved.length > 0 && (
        <section className="rounded border border-amber-500 p-3 space-y-2">
          <h5 className="font-semibold">Rows needing a layout check</h5>
          <p className="text-sm">
            These readings could not be placed fully in a statement table. Check
            each against the PDF and use the correction controls below.
          </p>
          {unresolved.map((row) => (
            <div
              key={row.id}
              data-statement-row={row.id}
              className={`flex flex-wrap gap-3 border-t py-2 ${row.id === selectedRowId ? "bg-amber-100/70 dark:bg-amber-900/30" : ""}`}
            >
              {row.source_cells.map((value) => (
                <span key={value.column_index}>{cell(row.id, value)}</span>
              ))}
              {onReviewRow && (
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => onReviewRow(row.id)}
                >
                  Review this row
                </Button>
              )}
              {rowTools?.(row.id) && (
                <div className="w-full">{rowTools(row.id)}</div>
              )}
            </div>
          ))}
        </section>
      )}
      {!sections.length && !positioned.length && (
        <p className="text-sm">
          A transaction table could not be reconstructed for this page. Check
          the original and the extracted text below.
        </p>
      )}
      {additional.length > 0 && (
        <details
          className="rounded border p-3"
          open={
            additional.some(
              (row) => row.id === selectedRowId && rowTools?.(row.id)
            ) || undefined
          }
        >
          <summary className="cursor-pointer font-medium">
            Other extracted page text ({additional.length} lines)
          </summary>
          <p className="text-sm py-2">
            Includes headings, notices and text outside the recognised table
            columns. This is extracted text, not a copy of the page layout.
          </p>
          {additional.map((row) => (
            <div
              key={row.id}
              className="flex flex-wrap gap-3 border-t py-2 text-sm"
            >
              {row.source_cells.map((value) => (
                <span key={value.column_index}>{cell(row.id, value)}</span>
              ))}
              {rowTools?.(row.id) && (
                <div className="w-full">{rowTools(row.id)}</div>
              )}
            </div>
          ))}
        </details>
      )}
    </div>
  )
}

// These statements print aligned lines without column headings. Keep each
// measured cell in its original horizontal position, including compound OCR
// cells, rather than manufacturing headers or splitting a source highlight.
function PositionedStatementRows({
  rows,
  onCell,
  selectedRowId,
  rowTools,
}: {
  rows: PrintedRow[]
  selectedRowId?: string
  onCell: (rowId: string, locator: unknown) => void
  rowTools?: (rowId: string) => ReactNode
}) {
  const box = (cell: PrintedCell) => {
    const value = (cell.locator as { rect?: number[] })?.rect
    return Array.isArray(value) &&
      value.length === 4 &&
      value.every(Number.isFinite)
      ? value
      : null
  }
  const boxes = rows
    .flatMap((row) => row.source_cells.map(box))
    .filter((b) => b !== null)
  if (!boxes.length) {
    return (
      <div className="space-y-2">
        {rows.map((row) => (
          <Fragment key={row.id}>
            <div
              key={row.id}
              data-statement-row={row.id}
              className={`flex flex-wrap gap-3 ${row.id === selectedRowId ? "bg-amber-100/70 dark:bg-amber-900/30" : ""}`}
            >
              {row.source_cells.map((cell) => (
                <button
                  type="button"
                  key={cell.column_index}
                  className="text-left whitespace-pre-wrap"
                  onClick={() => onCell(row.id, cell.locator)}
                >
                  {cell.expected_text}
                </button>
              ))}
            </div>
            {rowTools?.(row.id)}
          </Fragment>
        ))}
      </div>
    )
  }
  const left = Math.min(...boxes.map((b) => b[0]))
  const right = Math.max(...boxes.map((b) => b[2]))
  const column = (x: number) =>
    Math.min(
      1001,
      Math.max(
        1,
        1 + Math.round(((x - left) / Math.max(1, right - left)) * 1000)
      )
    )
  return (
    <div
      className="overflow-auto rounded border"
      role="group"
      aria-label="Extracted account section in printed positions"
    >
      <div className="min-w-[540px] p-3 font-mono text-[11px] leading-5">
        {rows.map((row) => (
          <Fragment key={row.id}>
            <div
              key={row.id}
              data-statement-row={row.id}
              className={`grid border-b border-border/30 py-1 ${row.id === selectedRowId ? "bg-amber-100/70 dark:bg-amber-900/30" : ""}`}
              style={{ gridTemplateColumns: "repeat(1000, minmax(0, 1fr))" }}
            >
              {row.source_cells.map((cell) => {
                const rect = box(cell)
                const numeric = /^[\d\s.,+\-/]+$/.test(cell.expected_text)
                return (
                  <button
                    key={cell.column_index}
                    type="button"
                    className="text-left whitespace-pre-wrap break-words hover:bg-accent focus-visible:outline-2 focus-visible:outline-primary"
                    style={
                      rect
                        ? {
                            gridColumn: `${column(rect[0])} / ${Math.max(column(rect[0]) + 1, column(rect[2]))}`,
                            whiteSpace: numeric ? "pre" : "pre-wrap",
                            textAlign:
                              numeric && rect[0] > left + (right - left) * 0.6
                                ? "right"
                                : "left",
                          }
                        : { gridColumn: "1 / -1" }
                    }
                    onClick={() => onCell(row.id, cell.locator)}
                  >
                    {cell.expected_text}
                  </button>
                )
              })}
            </div>
            {rowTools?.(row.id)}
          </Fragment>
        ))}
      </div>
    </div>
  )
}
