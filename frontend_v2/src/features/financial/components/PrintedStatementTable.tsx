type PrintedRow = {
  id: string
  page_number: number
  table_index: number
  row_index: number
  source_cells: {
    column_index: number
    expected_text: string
    locator: unknown
  }[]
}

export function PrintedStatementTable({
  rows,
  onCell,
}: {
  rows: PrintedRow[]
  onCell: (rowId: string, locator: unknown) => void
}) {
  const groups = new Map<string, PrintedRow[]>()
  for (const row of rows) {
    const key = `${row.page_number}:${row.table_index}`
    groups.set(key, [...(groups.get(key) ?? []), row])
  }
  return (
    <div className="space-y-4">
      {Array.from(groups.entries()).map(([key, tableRows]) => {
        const ordered = [...tableRows].sort((a, b) => a.row_index - b.row_index)
        const columns = Array.from(
          new Set(
            ordered.flatMap((row) =>
              row.source_cells.map((cell) => cell.column_index)
            )
          )
        ).sort((a, b) => a - b)
        return (
          <div key={key} className="overflow-auto">
            <table
              className="w-full border-collapse text-sm"
              aria-label={`Extracted printed table, page ${ordered[0].page_number}, table ${ordered[0].table_index + 1}`}
            >
              <caption className="text-left py-2 font-semibold">
                Page {ordered[0].page_number}
              </caption>
              <tbody>
                {ordered.map((row) => (
                  <tr key={row.id}>
                    {columns.map((column) => {
                      const cell = row.source_cells.find(
                        (item) => item.column_index === column
                      )
                      return (
                        <td
                          key={column}
                          className="border p-2 align-top whitespace-pre-wrap"
                        >
                          {cell?.expected_text ? (
                            <button
                              type="button"
                              className="text-left hover:bg-accent focus-visible:outline-2 focus-visible:outline-primary"
                              onClick={() => onCell(row.id, cell.locator)}
                            >
                              {cell.expected_text}
                            </button>
                          ) : null}
                        </td>
                      )
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )
      })}
    </div>
  )
}
