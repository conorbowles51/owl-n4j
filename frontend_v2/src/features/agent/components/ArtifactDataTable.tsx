import { useMemo, useState } from "react"
import { Button } from "@/components/ui/button"
import { AgentMarkdown } from "./AgentCitations"

import { artifactRows, artifactText } from "../artifact-data"
type Row = Record<string, unknown>
/** Model response pages are not dataset ceilings: every saved row and column stays reachable. */
export function ArtifactDataTable({ data, label, onRowSelect }: {
  data: Row; label: string; onRowSelect?: (row: Row) => void
}) {
  const [query, setQuery] = useState("")
  const [page, setPage] = useState(0)
  const [sort, setSort] = useState<{ key: string; descending: boolean } | null>(null)
  const rows = useMemo(() => artifactRows(data.rows || data.events || data.locations), [data])
  const columns = useMemo(() => {
    const declared = artifactRows(data.columns)
    const keys = new Set(declared.map((c) => artifactText(c.key)))
    const result = declared.map((c) => ({ key: artifactText(c.key), label: artifactText(c.label || c.key) }))
    for (const row of rows) for (const key of Object.keys(row)) {
      if (!keys.has(key)) { keys.add(key); result.push({ key, label: key.replaceAll("_", " ") }) }
    }
    return result
  }, [data.columns, rows])
  const filtered = useMemo(() => query.trim()
    ? rows.filter((row) => Object.values(row).some((v) => artifactText(v).toLocaleLowerCase().includes(query.toLocaleLowerCase())))
    : rows, [rows, query])
  const sorted = useMemo(() => sort ? [...filtered].sort((a, b) => {
    const left = a[sort.key]
    const right = b[sort.key]
    const difference = typeof left === "number" && typeof right === "number"
      ? left - right
      : artifactText(left).localeCompare(artifactText(right), undefined, { numeric: true, sensitivity: "base" })
    return sort.descending ? -difference : difference
  }) : filtered, [filtered, sort])
  const size = 50
  const lastPage = Math.max(0, Math.ceil(filtered.length / size) - 1)
  const currentPage = Math.min(page, lastPage)
  const start = currentPage * size
  return <section className="flex min-h-0 flex-col gap-2" aria-label={label}>
    <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
      <p aria-live="polite">{filtered.length ? `${start + 1}–${Math.min(start + size, filtered.length)} of ${filtered.length.toLocaleString()} rows` : "No matching rows"} · {columns.length} columns{query ? ` · ${rows.length.toLocaleString()} total rows` : ""}</p>
      <input aria-label={`Search ${label}`} value={query} onChange={(e) => { setQuery(e.target.value); setPage(0) }} placeholder="Search every row…" className="h-8 min-w-32 rounded-md border border-border bg-background px-2 text-foreground" />
    </div>
    <div className="max-h-[32rem] overflow-auto rounded-md border border-border">
      <table className="w-max min-w-full border-collapse text-xs">
        <caption className="sr-only">{label}</caption>
        <thead className="sticky top-0 z-10 bg-muted"><tr>{columns.map((c) => <th key={c.key} scope="col" aria-sort={sort?.key === c.key ? sort.descending ? "descending" : "ascending" : "none"} className="border-b border-border text-left font-semibold text-foreground"><button type="button" className="w-full px-3 py-2 text-left hover:bg-muted-foreground/10 focus-visible:outline-2 focus-visible:outline-primary" aria-label={`Sort by ${c.label}`} onClick={() => { setSort({ key: c.key, descending: sort?.key === c.key && !sort.descending }); setPage(0) }}>{c.label}<span aria-hidden="true" className="ml-2 text-muted-foreground">{sort?.key === c.key ? sort.descending ? "↓" : "↑" : "↕"}</span></button></th>)}</tr></thead>
        <tbody>{sorted.slice(start, start + size).map((row, index) => <tr key={start + index} className="even:bg-muted/20 hover:bg-muted/40">
          {columns.map((c, colIndex) => <td key={c.key} className="max-w-[28rem] min-w-24 border-b border-border/50 px-3 py-2 align-top leading-5 [overflow-wrap:anywhere]">
            {colIndex === 0 && onRowSelect ? <button type="button" onClick={() => onRowSelect(row)} className="text-left text-primary underline underline-offset-2">{artifactText(row[c.key]) || "Open record"}</button>
              : <AgentMarkdown content={artifactText(row[c.key])} className="text-xs leading-5 [&_p]:m-0" />}
          </td>)}
        </tr>)}</tbody>
      </table>
    </div>
    {lastPage > 0 && <div className="flex items-center justify-end gap-2">
      <Button size="sm" variant="outline" disabled={currentPage === 0} onClick={() => setPage(0)}>First</Button>
      <Button size="sm" variant="outline" disabled={currentPage === 0} onClick={() => setPage(currentPage - 1)}>Previous</Button>
      <span className="text-xs text-muted-foreground">Page {currentPage + 1} of {lastPage + 1}</span>
      <Button size="sm" variant="outline" disabled={currentPage === lastPage} onClick={() => setPage(currentPage + 1)}>Next</Button>
      <Button size="sm" variant="outline" disabled={currentPage === lastPage} onClick={() => setPage(lastPage)}>Last</Button>
    </div>}
  </section>
}
