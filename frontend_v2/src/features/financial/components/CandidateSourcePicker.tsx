import { proposePdfAccountReferences } from "../lib/pdf-account-references"
import { CandidatePageScan } from "./CandidatePageScan"
import { CandidateRowSuggestions } from "./CandidateRowSuggestions"
import { useRef, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { z } from "zod"
import { Button } from "@/components/ui/button"
import { fetchAPI } from "@/lib/api-client"
import {
  assertCandidateScope,
  candidateMapping,
  candidateUrl,
} from "../lib/candidate-contract"
import { proposePdfHeaders } from "../lib/pdf-header-proposals"
import { TransactionSourceHighlight } from "./TransactionSourceHighlight"

const index = z.number().int().nonnegative()
const sources = z.object({
  case_id: z.string(),
  offset: index,
  has_more: z.boolean(),
  items: z.array(
    z.object({
      evidence_file_id: z.string(),
      filename: z.string(),
      page_number: z.number().int().positive(),
    })
  ),
})
const sourceTable = z.object({
  case_id: z.string(),
  evidence_file_id: z.string(),
  page_number: z.number().int().positive(),
  table_index: index,
  table_count: z.number().int().positive(),
  source_revision: z.string().regex(/^[a-f0-9]{64}$/),
  table_source: z.enum(["drawn_geometry", "text_alignment"]),
  geometry_source: z.string(),
  text_origin: z
    .enum(["digital_text_layer", "recognised_glyphs", "unknown"])
    .default("unknown"),
  locator: z.unknown(),
  columns: z.array(index).max(64),
  rows: z
    .array(
      z.object({
        row_index: index,
        cells: z.array(
          z.object({
            column_index: index,
            expected_text: z.string().min(1).max(4096),
            locator: z.unknown(),
          })
        ),
      })
    )
    .max(1000),
  applied: z.literal(false),
})
const meanings = [
  ["unknown", "Unidentified"],
  ["amount", "Amount"],
  ["debit", "Money out"],
  ["credit", "Money in"],
  ["booking_date", "Booking date"],
  ["value_date", "Value date"],
  ["transaction_date", "Transaction date"],
  ["description", "Description"],
  ["reference", "Reference"],
  ["balance", "Balance"],
  ["account", "Account"],
  ["currency", "Currency"],
  ["direction", "Direction"],
] as const

export function CandidateSourcePicker({
  caseId,
  onSaved,
}: {
  caseId: string
  onSaved: (id: string) => void
}) {
  const [offset, setOffset] = useState(0)
  const [selected, setSelected] = useState<{
    file: string
    page: number
  } | null>(null)
  const list = useQuery({
    queryKey: ["financial-candidate-sources", caseId, offset],
    retry: false,
    queryFn: async () => {
      const data = sources.parse(
        await fetchAPI<unknown>(
          `${candidateUrl("candidate-sources", caseId)}&offset=${offset}`
        )
      )
      assertCandidateScope(data, caseId)
      if (data.offset !== offset)
        throw new Error("Source page list changed. Reload it.")
      return data
    },
  })
  return (
    <section
      aria-label="Choose PDF transaction rows"
      className="space-y-3 rounded border p-3"
    >
      <h3 className="font-semibold">Choose rows from a PDF</h3>
      <p>
        These are stored extraction results. Tables may contain summaries,
        letters or disclosures. Select only the rows you want to review as
        possible transactions.
      </p>
      <Button
        variant="outline"
        disabled={list.isFetching}
        onClick={() => void list.refetch()}
      >
        Refresh source pages
      </Button>
      {list.isError ? (
        <p role="alert">
          Source pages could not be loaded. {list.error.message}
        </p>
      ) : list.isPending ? (
        <p role="status">Loading source pages…</p>
      ) : (
        <>
          {list.data.items.length === 0 && (
            <p>
              No stored PDF table pages are available. The PDF must have
              completed text and table extraction first.
            </p>
          )}
          <ul
            aria-label="Available PDF source pages"
            className="max-h-64 space-y-2 overflow-auto"
          >
            {list.data.items.map((item) => (
              <li key={`${item.evidence_file_id}:${item.page_number}`}>
                <Button
                  variant="outline"
                  onClick={() =>
                    setSelected({
                      file: item.evidence_file_id,
                      page: item.page_number,
                    })
                  }
                >
                  {item.filename} · page {item.page_number}
                </Button>
              </li>
            ))}
          </ul>
          <div className="flex gap-2">
            <Button
              disabled={!offset}
              onClick={() => {
                setSelected(null)
                setOffset((n) => Math.max(0, n - 25))
              }}
            >
              Previous source pages
            </Button>
            <Button
              disabled={!list.data.has_more}
              onClick={() => {
                setSelected(null)
                setOffset((n) => n + 25)
              }}
            >
              Next source pages
            </Button>
          </div>
        </>
      )}
      {selected && (
        <CandidatePageScan
          key={selected.file}
          caseId={caseId}
          fileId={selected.file}
          onPage={(page) => setSelected({ ...selected, page })}
        />
      )}
      {selected && (
        <SourcePage
          key={`${caseId}:${selected.file}:${selected.page}`}
          caseId={caseId}
          file={selected.file}
          page={selected.page}
          onSaved={onSaved}
        />
      )}
    </section>
  )
}

function SourcePage({
  caseId,
  file,
  page,
  onSaved,
}: {
  caseId: string
  file: string
  page: number
  onSaved: (id: string) => void
}) {
  const [table, setTable] = useState(0)
  const [reload, setReload] = useState(0)
  const query = useQuery({
    queryKey: ["financial-candidate-source", caseId, file, page, table, reload],
    retry: false,
    refetchOnWindowFocus: false,
    queryFn: async () => {
      const data = sourceTable.parse(
        await fetchAPI<unknown>(
          `${candidateUrl(`candidate-sources/${encodeURIComponent(file)}/pages/${page}`, caseId)}&table_index=${table}`
        )
      )
      assertCandidateScope(data, caseId)
      if (
        data.evidence_file_id !== file ||
        data.page_number !== page ||
        data.table_index !== table ||
        data.table_count <= table
      )
        throw new Error("The source does not match the selected PDF table.")
      return data
    },
  })
  return (
    <div className="space-y-3">
      <Button variant="outline" onClick={() => setReload((n) => n + 1)}>
        Reload source and selection
      </Button>
      {query.isError ? (
        <p role="alert">Table could not be loaded. {query.error.message}</p>
      ) : query.isPending ? (
        <p role="status">Loading stored table…</p>
      ) : (
        <>
          <div className="flex items-center gap-2">
            <Button disabled={!table} onClick={() => setTable((n) => n - 1)}>
              Previous table
            </Button>
            <span>
              Table {table + 1} of {query.data.table_count}
            </span>
            <Button
              disabled={table + 1 >= query.data.table_count}
              onClick={() => setTable((n) => n + 1)}
            >
              Next table
            </Button>
          </div>
          <SourceSelection
            key={`${table}:${query.data.source_revision}:${reload}`}
            source={query.data}
            onSaved={onSaved}
          />
        </>
      )}
    </div>
  )
}

function SourceSelection({
  source,
  onSaved,
}: {
  source: z.infer<typeof sourceTable>
  onSaved: (id: string) => void
}) {
  const [focusedCell, setFocusedCell] = useState<{
    row: number
    column: number
    text: string
    locator: unknown
  } | null>(null)
  const [showHeaders, setShowHeaders] = useState(false)
  const headers = proposePdfHeaders(source.rows)
  const [showAccounts, setShowAccounts] = useState(false)
  const accountReferences = proposePdfAccountReferences(source.rows)
  const [selected, setSelected] = useState<number[]>([])
  const [columns, setColumns] = useState<Record<number, string>>({})
  const [page, setPage] = useState(0)
  const [blocked, setBlocked] = useState(false)
  const locked = useRef(false)
  const client = useQueryClient()
  const save = useMutation({
    retry: false,
    mutationFn: async () => {
      const proposal = {
        schema_version: "pdf-grid-mapping-v1",
        case_id: source.case_id,
        evidence_file_id: source.evidence_file_id,
        page_number: source.page_number,
        table_index: source.table_index,
        source_revision: source.source_revision,
        columns: source.columns.map((column_index) => ({
          column_index,
          meaning: columns[column_index] ?? "unknown",
        })),
        rows: source.rows
          .filter((r) => selected.includes(r.row_index))
          .map((r) => ({
            row_index: r.row_index,
            cells: r.cells.map((c) => ({
              column_index: c.column_index,
              expected_text: c.expected_text,
            })),
          })),
      }
      const raw = await fetchAPI<unknown>(
        candidateUrl("candidate-mappings", source.case_id),
        { method: "POST", body: proposal }
      )
      const data = candidateMapping.parse(raw)
      const echoed = z
        .object({
          original: z.object({
            proposal: z.object({
              source_revision: z.string(),
              page_number: index,
              table_index: index,
              columns: z.array(
                z.object({ column_index: index, meaning: z.string() })
              ),
              rows: z.array(
                z.object({
                  row_index: index,
                  cells: z.array(
                    z.object({ column_index: index, expected_text: z.string() })
                  ),
                })
              ),
            }),
          }),
        })
        .parse(raw).original.proposal
      assertCandidateScope(data, source.case_id)
      if (
        data.evidence_file_id !== source.evidence_file_id ||
        data.original.proposal.case_id !== source.case_id ||
        data.original.proposal.evidence_file_id !== source.evidence_file_id ||
        echoed.source_revision !== proposal.source_revision ||
        echoed.page_number !== proposal.page_number ||
        echoed.table_index !== proposal.table_index ||
        JSON.stringify(echoed.columns) !== JSON.stringify(proposal.columns) ||
        JSON.stringify(echoed.rows) !== JSON.stringify(proposal.rows) ||
        data.candidates.length !== proposal.rows.length
      )
        throw new Error(
          "The saved response does not match your selection. Reload saved readings to check the outcome."
        )
      return data
    },
    onSuccess: (data) => onSaved(data.id),
    onSettled: () => {
      setBlocked(true)
      void client.invalidateQueries({
        queryKey: ["financial-candidates", source.case_id, "list"],
      })
    },
  })
  const disabled = blocked || save.isPending
  return (
    <div className="space-y-3">
      <p>
        {source.table_source === "text_alignment"
          ? "Rows inferred from text spacing. Check their grouping against the page."
          : "Table found from drawn lines. Check which rows contain transactions."}
      </p>
      <p
        aria-label="Stored page text origin"
        className="rounded border p-2 text-sm"
      >
        {source.text_origin === "digital_text_layer"
          ? "Stored text came from the PDF text layer. Inspect the original to confirm row grouping and meaning."
          : source.text_origin === "recognised_glyphs"
            ? "Stored text was recognised from an image (OCR). Check decimal points, signs, dates and account characters against the original; recognition can omit or misread them."
            : "Stored text origin is unknown. Check every proposed value against the original; this page is not treated as digitally verified."}{" "}
        Page origin does not confirm any transaction or promote its reliability.
      </p>
      <div className="grid items-start gap-4 lg:grid-cols-2">
        <section
          aria-label="Original document beside row selection"
          className="min-w-0 space-y-3 rounded border p-3 lg:sticky lg:top-4"
        >
          <h4 className="font-semibold">
            Original document · page {source.page_number}
          </h4>
          <p className="text-sm">
            Click a table value to locate it on the page. Checking a location
            does not select the row or verify its reading.
          </p>
          {focusedCell && (
            <div className="space-y-2 text-sm">
              <p>
                Source row {focusedCell.row + 1}, column{" "}
                {focusedCell.column + 1}: {focusedCell.text}
              </p>
              <Button variant="outline" onClick={() => setFocusedCell(null)}>
                Show table location
              </Button>
            </div>
          )}
          <TransactionSourceHighlight
            sourceDocumentId={source.evidence_file_id}
            locatorPayload={focusedCell ? focusedCell.locator : source.locator}
          />
        </section>
        <fieldset disabled={disabled} className="min-w-0 space-y-3">
          <Button variant="outline" onClick={() => setShowHeaders((v) => !v)}>
            {showHeaders
              ? "Hide column suggestions"
              : "Suggest column meanings"}
          </Button>
          {showHeaders && (
            <div className="space-y-2 rounded border p-3">
              <p>
                Checked the first {headers.checkedRows} stored rows for exact
                column labels.
                {headers.hasMore ? " Later rows were not checked." : ""} Matches
                are suggestions, not proof of a header or transaction. Generic
                “Date” does not establish a date role. Applying a meaning does
                not select any rows.
              </p>
              {headers.proposals.length === 0 && (
                <p>
                  No supported exact labels found. Assign meanings manually from
                  the source.
                </p>
              )}
              {headers.proposals.map((header) => (
                <div key={`${header.column}:${header.meaning}`}>
                  <p>
                    Source row {header.row + 1}, column {header.column + 1}: “
                    {header.text}”
                  </p>
                  <Button
                    variant="outline"
                    onClick={() =>
                      setColumns((v) => ({
                        ...v,
                        [header.column]: header.meaning,
                      }))
                    }
                  >
                    Use {header.label} for column {header.column + 1}
                  </Button>
                </div>
              ))}
            </div>
          )}

          <Button variant="outline" onClick={() => setShowAccounts((v) => !v)}>
            {showAccounts
              ? "Hide printed account references"
              : "Inspect printed account references"}
          </Button>
          {showAccounts && (
            <section
              aria-label="Printed account reference proposals"
              className="space-y-2 rounded border p-3"
            >
              <p>
                Checked {accountReferences.checkedRows} stored rows for labelled
                account/card numbers or ending digits.
                {accountReferences.hasMore
                  ? " Later rows were not checked."
                  : ""}{" "}
                These are source-text proposals, not verified identities.
                Partial numbers cannot identify an account by themselves. Review
                the original, then explicitly choose or create the appropriate
                account during row review.
              </p>
              {!accountReferences.references.length && (
                <p>
                  No supported labelled reference found in these rows. Inspect
                  the original for account context; absence here does not mean
                  no account is present.
                </p>
              )}
              {accountReferences.distinctReferences > 1 && (
                <p>
                  Several different printed references were found. They may
                  concern different accounts or different representations of one
                  account; no association has been inferred.
                </p>
              )}
              {accountReferences.references.map((reference) => (
                <div
                  key={`${reference.row}:${reference.column}`}
                  className="space-y-1"
                >
                  <p>
                    Printed {reference.partial ? "partial " : ""}reference:{" "}
                    {reference.reference}
                  </p>
                  <Button
                    variant="outline"
                    onClick={() => setFocusedCell(reference)}
                  >
                    Inspect account reference at row {reference.row + 1}, column{" "}
                    {reference.column + 1}
                  </Button>
                </div>
              ))}
            </section>
          )}

          <div className="grid gap-2 sm:grid-cols-3">
            {source.columns.map((column) => (
              <label key={column}>
                Column {column + 1} meaning
                <select
                  aria-label={`Column ${column + 1} meaning`}
                  className="block w-full rounded border bg-background p-2"
                  value={columns[column] ?? "unknown"}
                  onChange={(e) =>
                    setColumns((v) => ({ ...v, [column]: e.target.value }))
                  }
                >
                  {meanings.map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </select>
              </label>
            ))}
          </div>
          <CandidateRowSuggestions
            source={source}
            columns={columns}
            onSelect={(rows) =>
              setSelected((current) => [...new Set([...current, ...rows])])
            }
          />
          <div className="overflow-auto">
            <table className="w-full text-left text-xs">
              <thead>
                <tr>
                  <th>Use row</th>
                  {source.columns.map((c) => (
                    <th key={c}>Column {c + 1}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {source.rows.slice(page * 25, page * 25 + 25).map((row) => (
                  <tr key={row.row_index}>
                    <td className="p-2">
                      <label>
                        <input
                          type="checkbox"
                          aria-label={`Select source row ${row.row_index + 1}`}
                          checked={selected.includes(row.row_index)}
                          onChange={(e) =>
                            setSelected((v) =>
                              e.target.checked
                                ? [...v, row.row_index]
                                : v.filter((n) => n !== row.row_index)
                            )
                          }
                        />{" "}
                        {row.row_index + 1}
                      </label>
                    </td>
                    {source.columns.map((c) => (
                      <td
                        className="max-w-72 whitespace-pre-wrap break-words border p-2"
                        key={c}
                      >
                        {row.cells
                          .filter((cell) => cell.column_index === c)
                          .map((cell) => (
                            <button
                              key={cell.column_index}
                              type="button"
                              aria-label={`Show source row ${row.row_index + 1}, column ${c + 1}`}
                              aria-pressed={
                                focusedCell?.row === row.row_index &&
                                focusedCell.column === c
                              }
                              className="w-full rounded p-1 text-left hover:bg-muted focus-visible:outline focus-visible:outline-2 focus-visible:outline-ring aria-pressed:bg-muted"
                              onClick={() =>
                                setFocusedCell({
                                  row: row.row_index,
                                  column: c,
                                  text: cell.expected_text,
                                  locator: cell.locator,
                                })
                              }
                            >
                              {cell.expected_text}
                            </button>
                          ))}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="flex gap-2">
            <Button disabled={!page} onClick={() => setPage((n) => n - 1)}>
              Previous table rows
            </Button>
            <Button
              disabled={(page + 1) * 25 >= source.rows.length}
              onClick={() => setPage((n) => n + 1)}
            >
              Next table rows
            </Button>
          </div>
        </fieldset>
      </div>
      <p>
        {selected.length} rows selected. Column meanings are proposals; amounts
        and dates are not converted here. Saved readings stay outside ledger
        totals.
      </p>
      <Button
        disabled={disabled || !selected.length}
        onClick={() => {
          if (locked.current) return
          locked.current = true
          save.mutate()
        }}
      >
        Save selected rows for review
      </Button>
      {save.isError && (
        <p role="alert">
          Save could not be confirmed. {save.error.message} Reload saved
          readings before retrying.
        </p>
      )}
      {save.isSuccess && (
        <p role="status">
          Rows saved. Open the saved readings below to review them.
        </p>
      )}
    </div>
  )
}
