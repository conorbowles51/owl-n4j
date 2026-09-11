import {
  printedStatementSections,
  type PrintedCell,
  type PrintedRow,
} from "../lib/printed-statement-sections"

export function PrintedStatementTable({
  rows,
  onCell,
}: {
  rows: PrintedRow[]
  onCell: (rowId: string, locator: unknown) => void
}) {
  const { sections, remaining } = printedStatementSections(rows)
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
                    {section.headers.map((header) => (
                      <th
                        key={header.column_index}
                        className="border p-2 text-left"
                      >
                        {cell(section.key, header)}
                      </th>
                    ))}
                  </tr>
                </thead>
              )}
              <tbody>
                {section.rows.map(({ row, cells }) => (
                  <tr key={row.id}>
                    {cells.map((value, index) => (
                      <td key={index} className="border p-2 align-top">
                        {cell(row.id, value)}
                      </td>
                    ))}
                  </tr>
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
            <div key={row.id} className="flex flex-wrap gap-3 border-t py-2">
              {row.source_cells.map((value) => (
                <span key={value.column_index}>{cell(row.id, value)}</span>
              ))}
            </div>
          ))}
        </section>
      )}
      {!sections.length && (
        <p className="text-sm">
          A transaction table could not be reconstructed for this page. Check
          the original and the extracted text below.
        </p>
      )}
      {additional.length > 0 && (
        <details className="rounded border p-3">
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
            </div>
          ))}
        </details>
      )}
    </div>
  )
}
