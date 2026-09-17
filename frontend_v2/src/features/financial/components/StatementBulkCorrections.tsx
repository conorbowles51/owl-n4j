import { useMemo, useState, type ReactNode } from "react"
import { Button } from "@/components/ui/button"
import {
  correctionValue,
  previewCorrections,
  type CorrectionAction,
  type ReviewEdit,
} from "../lib/statement-bulk-correction"

export function StatementBulkCorrections({
  rows,
  apply,
  inspect,
  reassign,
}: {
  rows: ReviewEdit[]
  apply: (changes: ReturnType<typeof previewCorrections>) => void
  inspect: (id: string) => void
  reassign?: (rowIds: string[], reason: string) => ReactNode
}) {
  const [open, setOpen] = useState(false)
  const [search, setSearch] = useState("")
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [action, setAction] = useState<CorrectionAction | "reassign">("exclude")
  const [value, setValue] = useState("")
  const [reason, setReason] = useState("")
  const [page, setPage] = useState(0)
  const [preview, setPreview] = useState<ReturnType<
    typeof previewCorrections
  > | null>(null)
  const [error, setError] = useState("")
  const [message, setMessage] = useState("")
  const filtered = useMemo(
    () =>
      rows.filter((row) =>
        `${row.date} ${row.description} ${row.counterparty}`
          .toLowerCase()
          .includes(search.toLowerCase())
      ),
    [rows, search]
  )
  const size = 30
  const pageCount = Math.max(
    1,
    Math.ceil((preview?.length ?? filtered.length) / size)
  )
  const currentPage = Math.min(page, pageCount - 1)
  const currentRows = filtered.slice(
    currentPage * size,
    (currentPage + 1) * size
  )
  const byId = useMemo(() => new Map(rows.map((row) => [row.id, row])), [rows])
  const stale =
    !!preview &&
    preview.some((change) => byId.get(change.before.id) !== change.before)
  const resetPreview = () => {
    setPreview(null)
    setError("")
    setMessage("")
    setPage(0)
  }
  return (
    <section
      className="my-3 rounded border bg-card p-3 space-y-3"
      aria-label="Correct several statement rows"
    >
      <Button size="sm" variant="outline" onClick={() => setOpen(!open)}>
        {open ? "Close selected-row corrections" : "Correct several rows"}
      </Button>
      {message && (
        <p role="status" className="text-sm">
          {message}
        </p>
      )}
      {open && (
        <>
          <p className="text-sm">
            Select transactions with the same error, choose a correction and
            check the preview before applying it. Original readings are
            retained.
          </p>
          <div className="flex flex-wrap gap-3 items-end text-sm">
            <label>
              Find transactions
              <input
                className="block border rounded bg-background p-2 mt-1"
                value={search}
                onChange={(event) => {
                  setSearch(event.target.value)
                  setPage(0)
                  setPreview(null)
                }}
              />
            </label>
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                setSelected(new Set(filtered.map((row) => row.id)))
                resetPreview()
              }}
            >
              Select all {filtered.length} matching rows
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                setSelected(new Set())
                resetPreview()
              }}
            >
              Clear row selection
            </Button>
            <span>{selected.size} selected across this statement</span>
          </div>
          <div className="flex flex-wrap gap-3 items-end text-sm">
            <label>
              Correction
              <select
                aria-label="Correction"
                className="block border rounded bg-background p-2 mt-1"
                value={action}
                onChange={(event) => {
                  setAction(event.target.value as CorrectionAction | "reassign")
                  setValue("")
                  resetPreview()
                }}
              >
                <option value="exclude">Exclude from import</option>
                <option value="include">Include in import</option>
                <option value="switch">Switch credit and debit</option>
                <option value="date">Set transaction date</option>
                <option value="counterparty">Set paid by / paid to</option>
                {reassign && (
                  <option value="reassign">
                    Move to another account or period
                  </option>
                )}
              </select>
            </label>
            {(action === "date" || action === "counterparty") && (
              <label>
                {action === "date" ? "Correct date" : "Correct name"}
                <input
                  type={action === "date" ? "date" : "text"}
                  className="block border rounded bg-background p-2 mt-1"
                  value={value}
                  onChange={(event) => {
                    setValue(event.target.value)
                    resetPreview()
                  }}
                />
              </label>
            )}
            <label className="grow">
              Reason for these corrections
              <input
                maxLength={2000}
                className="block w-full border rounded bg-background p-2 mt-1"
                value={reason}
                onChange={(event) => {
                  setReason(event.target.value)
                  resetPreview()
                }}
              />
            </label>
            {action !== "reassign" && (
              <Button
                size="sm"
                variant="outline"
                disabled={!selected.size}
                onClick={() => {
                  try {
                    setPreview(
                      previewCorrections(rows, selected, action, value, reason)
                    )
                    setPage(0)
                    setError("")
                  } catch (err) {
                    setError((err as Error).message)
                  }
                }}
              >
                Preview corrections
              </Button>
            )}
          </div>
          {error && (
            <p role="alert" className="text-sm">
              {error}
            </p>
          )}
          {stale && (
            <p role="alert" className="text-sm">
              Values changed after this preview. Preview the corrections again
              before applying.
            </p>
          )}
          <div className="overflow-x-auto max-h-72 overflow-y-auto">
            <table
              className="w-full text-sm"
              aria-label={
                preview
                  ? "Correction preview"
                  : "Transactions for selected-row correction"
              }
            >
              <thead className="sticky top-0 bg-card">
                <tr>
                  <th className="p-2 text-left">
                    {preview ? "Date" : "Select"}
                  </th>
                  <th className="p-2 text-left">Transaction</th>
                  <th className="p-2 text-left">
                    Current {action === "switch" ? "column" : "value"}
                  </th>
                  {preview && (
                    <th className="p-2 text-left">After correction</th>
                  )}
                  <th className="p-2 text-left">Source</th>
                </tr>
              </thead>
              <tbody>
                {preview
                  ? preview
                      .slice(currentPage * size, (currentPage + 1) * size)
                      .map(({ before, after }) => (
                        <tr key={before.id} className="border-t">
                          <td className="p-2">{before.date}</td>
                          <td className="p-2">{before.description}</td>
                          <td className="p-2">
                            {correctionValue(
                              before,
                              action === "reassign" ? "date" : action
                            )}
                          </td>
                          <td className="p-2 font-medium">
                            {correctionValue(
                              after,
                              action === "reassign" ? "date" : action
                            )}
                          </td>
                          <td>
                            <Button
                              size="sm"
                              variant="ghost"
                              onClick={() => inspect(before.id)}
                            >
                              View original
                            </Button>
                          </td>
                        </tr>
                      ))
                  : currentRows.map((row) => (
                      <tr key={row.id} className="border-t">
                        <td className="p-2">
                          <input
                            type="checkbox"
                            aria-label={`Select correction row ${row.id}`}
                            checked={selected.has(row.id)}
                            onChange={(event) => {
                              setSelected((old) => {
                                const next = new Set(old)
                                if (event.target.checked) next.add(row.id)
                                else next.delete(row.id)
                                return next
                              })
                              setPreview(null)
                              setMessage("")
                            }}
                          />
                        </td>
                        <td className="p-2">
                          {row.date} · {row.description}
                        </td>
                        <td className="p-2">
                          {correctionValue(
                            row,
                            action === "reassign" ? "date" : action
                          )}
                        </td>
                        <td>
                          <Button
                            size="sm"
                            variant="ghost"
                            onClick={() => inspect(row.id)}
                          >
                            View original
                          </Button>
                        </td>
                      </tr>
                    ))}
              </tbody>
            </table>
          </div>
          {pageCount > 1 && (
            <div className="flex items-center gap-2 text-sm">
              <Button
                size="sm"
                variant="outline"
                disabled={!currentPage}
                onClick={() => setPage(currentPage - 1)}
              >
                Previous correction page
              </Button>
              <span>
                Page {currentPage + 1} of {pageCount}
              </span>
              <Button
                size="sm"
                variant="outline"
                disabled={currentPage + 1 >= pageCount}
                onClick={() => setPage(currentPage + 1)}
              >
                Next correction page
              </Button>
            </div>
          )}
          {action === "reassign" && reassign?.([...selected], reason)}
          {preview && (
            <div className="space-y-2">
              <p className="text-sm">
                {preview.length} rows will change.{" "}
                {selected.size - preview.length} selected rows already have the
                requested value. The statement will be checked again after
                applying.
              </p>
              <Button
                disabled={stale}
                onClick={() => {
                  apply(preview)
                  setMessage(
                    `Applied corrections to ${preview.length} rows. Save progress or confirm the import to record them in the case.`
                  )
                  setPreview(null)
                  setSelected(new Set())
                  setOpen(false)
                }}
              >
                Apply corrections to {preview.length} rows
              </Button>
            </div>
          )}
        </>
      )}
    </section>
  )
}
