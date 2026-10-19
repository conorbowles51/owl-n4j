import { proposeStatementControls } from "../lib/statement-control-proposals"
import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { z } from "zod"
import { Button } from "@/components/ui/button"
import { fetchAPI } from "@/lib/api-client"
import { candidateUrl, assertCandidateScope } from "../lib/candidate-contract"
import { type ControlCell } from "../lib/statement-scope-contract"
import { TransactionSourceHighlight } from "./TransactionSourceHighlight"
const tableSchema = z.object({
  case_id: z.string(),
  evidence_file_id: z.string(),
  page_number: z.number().int().positive(),
  table_index: z.number().int().nonnegative(),
  table_count: z.number().int().positive(),
  source_revision: z.string().regex(/^[a-f0-9]{64}$/),
  locator: z.unknown(),
  applied: z.literal(false),
  rows: z
    .array(
      z.object({
        row_index: z.number().int().nonnegative(),
        cells: z.array(
          z.object({
            column_index: z.number().int().nonnegative(),
            expected_text: z.string().min(1),
            locator: z.unknown(),
          })
        ),
      })
    )
    .max(1000),
})
export function StatementControlPicker({
  caseId,
  fileId,
  label,
  onSelected,
  onClose,
}: {
  caseId: string
  fileId: string
  label: string
  onSelected: (cell: ControlCell) => void
  onClose: () => void
}) {
  const [entry, setEntry] = useState("1"),
    [page, setPage] = useState(1),
    [table, setTable] = useState(0)
  const query = useQuery({
    queryKey: [
      "financial-statement-control-source",
      caseId,
      fileId,
      page,
      table,
    ],
    retry: false,
    refetchOnWindowFocus: false,
    queryFn: async () => {
      const data = tableSchema.parse(
        await fetchAPI<unknown>(
          `${candidateUrl(`candidate-sources/${encodeURIComponent(fileId)}/pages/${page}`, caseId)}&table_index=${table}`
        )
      )
      assertCandidateScope(data, caseId)
      if (
        data.evidence_file_id !== fileId ||
        data.page_number !== page ||
        data.table_index !== table ||
        data.table_count <= table
      )
        throw new Error("Source does not match this PDF page and table.")
      return data
    },
  })
  return (
    <section
      className="space-y-3 rounded border p-3"
      aria-label={`Choose source for ${label}`}
    >
      <h4 className="font-semibold">Choose the printed source for {label}</h4>
      <p>
        Select the original cell containing this control. Its text and location
        will be preserved separately from your reading.
      </p>
      <div className="flex flex-wrap items-end gap-2">
        <label>
          Source PDF page
          <input
            aria-label="Statement control source page"
            type="number"
            min={1}
            value={entry}
            onChange={(e) => setEntry(e.target.value)}
            className="block rounded border bg-background p-2"
          />
        </label>
        <Button
          variant="outline"
          disabled={
            !/^[1-9][0-9]*$/.test(entry) || !Number.isSafeInteger(Number(entry))
          }
          onClick={() => {
            setPage(Number(entry))
            setTable(0)
          }}
        >
          Load control page
        </Button>
        <Button variant="outline" onClick={onClose}>
          Close control source
        </Button>
      </div>
      {query.isPending ? (
        <p role="status">Loading control source…</p>
      ) : query.isError ? (
        <p role="alert">Control source unavailable. {query.error.message}</p>
      ) : (
        <>
          <div className="flex gap-2">
            <Button disabled={!table} onClick={() => setTable((v) => v - 1)}>
              Previous control table
            </Button>
            <span>
              Table {table + 1} of {query.data.table_count}
            </span>
            <Button
              disabled={table + 1 >= query.data.table_count}
              onClick={() => setTable((v) => v + 1)}
            >
              Next control table
            </Button>
          </div>
          <ControlTable
            key={`${page}:${table}:${query.data.source_revision}`}
            fileId={fileId}
            label={label}
            data={query.data}
            onSelected={onSelected}
          />
        </>
      )}
    </section>
  )
}
function ControlTable({
  fileId,
  label,
  data,
  onSelected,
}: {
  fileId: string
  label: string
  data: z.infer<typeof tableSchema>
  onSelected: (cell: ControlCell) => void
}) {
  const [rowPage, setRowPage] = useState(0)
  const [selected, setSelected] = useState<{
    cell: ControlCell
    locator: unknown
  } | null>(null)
  const [showProposals, setShowProposals] = useState(false)
  const [proposalPage, setProposalPage] = useState(0)
  const proposals = proposeStatementControls(data.rows, label)
  const inspect = (
    row: number,
    cell: { column_index: number; expected_text: string; locator: unknown }
  ) => {
    setSelected({
      cell: {
        page_number: data.page_number,
        table_index: data.table_index,
        row_index: row,
        column_index: cell.column_index,
        source_revision: data.source_revision,
        expected_text: cell.expected_text,
      },
      locator: cell.locator,
    })
    setRowPage(Math.floor(data.rows.findIndex((r) => r.row_index === row) / 25))
  }
  return (
    <div className="grid items-start gap-3 lg:grid-cols-2">
      <div className="min-w-0 space-y-2 lg:sticky lg:top-4">
        <TransactionSourceHighlight
          sourceDocumentId={fileId}
          locatorPayload={selected ? selected.locator : data.locator}
        />
        {selected && (
          <>
            <p>Original text: {selected.cell.expected_text}</p>
            <Button onClick={() => onSelected(selected.cell)}>
              Use this control cell
            </Button>
          </>
        )}
      </div>
      <div
        className="max-h-[650px] space-y-1 overflow-auto"
        aria-label="Stored control cells"
      >
        <Button variant="outline" onClick={() => setShowProposals((v) => !v)}>
          {showProposals
            ? "Hide labelled control candidates"
            : "Find labelled control candidates"}
        </Button>
        {showProposals && (
          <section
            aria-label="Labelled control candidates"
            className="space-y-2 rounded border p-2"
          >
            <p>
              Exact printed labels only. Review the account, period and meaning
              on the original. Several values or repeated labels remain separate
              choices; no reading is filled in.
            </p>
            {!proposals.length && (
              <p>
                No supported label and value found on this table. Inspect the
                stored cells manually.
              </p>
            )}
            <p>
              {proposals.length} labelled rows; page {proposalPage + 1} of{" "}
              {Math.max(1, Math.ceil(proposals.length / 10))}.
            </p>
            {proposals
              .slice(proposalPage * 10, proposalPage * 10 + 10)
              .map((p) => (
                <div key={p.row} className="space-y-1 border-t pt-1">
                  <p>
                    Row {p.row + 1}: {p.label.expected_text}
                  </p>
                  {p.values.map((c) => (
                    <Button
                      key={c.column_index}
                      variant="outline"
                      className="max-w-full whitespace-normal"
                      onClick={() => inspect(p.row, c)}
                    >
                      Inspect control candidate row {p.row + 1}, column{" "}
                      {c.column_index + 1}: {c.expected_text}
                    </Button>
                  ))}
                </div>
              ))}
            <Button
              variant="outline"
              disabled={!proposalPage}
              onClick={() => setProposalPage((p) => p - 1)}
            >
              Previous control candidates
            </Button>
            <Button
              variant="outline"
              disabled={(proposalPage + 1) * 10 >= proposals.length}
              onClick={() => setProposalPage((p) => p + 1)}
            >
              Next control candidates
            </Button>
          </section>
        )}
        {data.rows.slice(rowPage * 25, rowPage * 25 + 25).map((row) => (
          <div
            key={row.row_index}
            className="flex flex-wrap gap-1 border-b p-1"
          >
            <span className="text-xs">Row {row.row_index + 1}</span>
            {row.cells.map((cell) => (
              <button
                type="button"
                key={cell.column_index}
                aria-label={`Control row ${row.row_index + 1}, column ${cell.column_index + 1}`}
                aria-pressed={
                  selected?.cell.row_index === row.row_index &&
                  selected.cell.column_index === cell.column_index
                }
                className="max-w-full rounded border p-2 text-left text-xs break-words hover:bg-muted aria-pressed:bg-muted"
                onClick={() =>
                  setSelected({
                    cell: {
                      page_number: data.page_number,
                      table_index: data.table_index,
                      row_index: row.row_index,
                      column_index: cell.column_index,
                      source_revision: data.source_revision,
                      expected_text: cell.expected_text,
                    },
                    locator: cell.locator,
                  })
                }
              >
                {cell.expected_text}
              </button>
            ))}
          </div>
        ))}
        <div className="flex gap-2">
          <Button
            disabled={!rowPage}
            onClick={() => setRowPage((value) => value - 1)}
          >
            Previous control rows
          </Button>
          <Button
            disabled={(rowPage + 1) * 25 >= data.rows.length}
            onClick={() => setRowPage((value) => value + 1)}
          >
            Next control rows
          </Button>
        </div>
      </div>
    </div>
  )
}
