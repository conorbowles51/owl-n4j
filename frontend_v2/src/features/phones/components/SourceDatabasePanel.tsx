import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { Button } from "@/components/ui/button"
import { ProgressPanel } from "@/components/ui/progress-panel"
import { useProgressClock } from "@/components/ui/use-progress-clock"
import { failureText, getSourceDatabase } from "../api"
import type { RawValue, RecordDetail, SourceDatabase } from "../schemas"

/** 05 section 17.2 / 03 section 3.6 point 6: the record's source line, and the app database row it was read from.
 *  Everything shown here is read from the database file by Loupe's read-only viewer, never the report's record. */
export function SourceDatabasePanel({ caseId, detail }: { caseId?: string; detail: RecordDetail }) {
  const row = detail.source_row
  const [open, setOpen] = useState(false)
  if (!row.available) {
    return (
      <section aria-label="Source database" className="text-xs">
        <p>{row.reason}</p>
        {(row.files ?? []).map((f) => (
          <p key={f.file_uid} className="break-all text-muted-foreground">
            {f.original_path ?? "(no path in the report)"}: {f.state_words}
          </p>
        ))}
      </section>
    )
  }
  return (
    <section aria-label="Source database" className="space-y-1 text-xs">
      {!row.row_named && <p>{row.reason}</p>}
      {!caseId ? null : !open ? (
        <Button size="sm" variant="outline" onClick={() => setOpen(true)}>
          {row.row_named ? "Open source row" : "Open source database"}
        </Button>
      ) : (
        <SourceView caseId={caseId} recordUid={detail.record_uid} source={row.source_index ?? 0} />
      )}
    </section>
  )
}

function SourceView({ caseId, recordUid, source }: { caseId: string; recordUid: string; source: number }) {
  const [browse, setBrowse] = useState<string | undefined>(undefined)
  const [page, setPage] = useState(1)
  const [startedAt, setStartedAt] = useState(() => performance.now())
  const q = useQuery({
    queryKey: ["phone-source-db", caseId, recordUid, source, browse ?? "", page],
    queryFn: () => getSourceDatabase(caseId, recordUid, source, browse, page),
    staleTime: 60_000,
  })
  // ticks when the panel is due (300 ms after the press), then every 500 ms while the copy is being opened
  const now = useProgressClock(q.isFetching, startedAt, 500)
  if (q.isError) {
    return (
      <div role="alert">
        <p>{failureText(q.error, "The app database could not be opened.")}</p>
        <Button size="sm" variant="outline" onClick={() => { setStartedAt(performance.now()); void q.refetch() }}>Try again</Button>
      </div>
    )
  }
  if (!q.data) {
    return (
      <ProgressPanel
        progress={{ step: "Copying the app database and opening the copy read-only", startedAt, movedAt: startedAt }}
        now={now}
        onRetry={() => { setStartedAt(performance.now()); void q.refetch() }}
      />
    )
  }
  return <SourceBody data={q.data} browse={browse} onBrowse={(t, p) => { setStartedAt(performance.now()); setBrowse(t); setPage(p) }} busy={q.isFetching} />
}

export function SourceBody({ data, browse, onBrowse, busy }: {
  data: SourceDatabase; browse?: string; onBrowse: (table: string | undefined, page: number) => void; busy?: boolean
}) {
  const path = data.source.file?.original_path ?? "(no path in the report)"
  if (data.refused || !data.view) return <p role="alert">{data.refused}</p>
  const v = data.view
  const nr = v.named_row
  return (
    <div className="space-y-2 rounded border p-2" data-testid="source-database">
      <p className="font-medium">Read from the app database {path} by Loupe's read-only viewer; this is the file's content, not the report's record.</p>
      <p className="text-muted-foreground">
        Opened {v.open_mode}, from a copy whose SHA-256 is {v.copy.sha256} ({v.copy.size.toLocaleString("en-US")} bytes)
        {v.copy.siblings.length > 0 ? `; copied with it: ${v.copy.siblings.map((s) => `${s.suffix} (${s.size.toLocaleString("en-US")} bytes)`).join(", ")}` : "; no log or journal file beside it"}.
        {" "}SQLite {v.opened_by.sqlite}.
      </p>
      {(data.source.table_name || data.source.offset) && (
        <p>
          The report says this record came from {data.source.table_name ? `table ${data.source.table_name}` : "this file"}
          {data.source.offset ? `, at byte ${Number(data.source.offset).toLocaleString("en-US")} of the file` : ", with no position given"}.
        </p>
      )}
      {nr && nr.found && <p>The row holding that byte: row {nr.rowid} of table {nr.table}.</p>}
      {nr?.note && <p>{nr.note}</p>}
      {nr?.log_note && <p className="text-muted-foreground">{nr.log_note}</p>}
      {nr && !nr.found && <p>{nr.reason}</p>}
      {nr?.bytes_at_position && (
        <p className="break-all text-muted-foreground">The bytes at that position, as they are: <Raw value={nr.bytes_at_position} /></p>
      )}
      {nr && nr.found && nr.columns && nr.values && (
        <table aria-label="Source row" className="w-full table-fixed border-collapse">
          <tbody>
            {nr.columns.map((c, k) => (
              <tr key={c} className="border-t align-top">
                <th scope="row" className="w-1/3 break-all pr-2 text-left font-normal text-muted-foreground">{c}</th>
                <td className="break-all"><Raw value={nr.values![k]} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <details>
        <summary>Tables in this database ({v.tables.length})</summary>
        <ul>
          {v.tables.map((t) => (
            <li key={t.name}>
              <button type="button" className="underline" onClick={() => onBrowse(t.name, 1)}>{t.name}</button>
              {" "}{t.type === "view" ? "(view) " : ""}{t.row_count != null ? `${t.row_count.toLocaleString("en-US")} rows` : t.count_note}
            </li>
          ))}
        </ul>
      </details>
      {v.page && (
        <div aria-label={`Rows of ${v.page.table}`}>
          <p>
            {v.page.table}: rows {v.page.total === 0 ? 0 : ((v.page.page - 1) * v.page.page_rows + 1).toLocaleString("en-US")} to{" "}
            {Math.min(v.page.page * v.page.page_rows, v.page.total).toLocaleString("en-US")} of {v.page.total.toLocaleString("en-US")}
            {busy ? " (loading)" : ""}
          </p>
          <div className="flex gap-2">
            <Button size="sm" variant="outline" disabled={v.page.page <= 1} onClick={() => onBrowse(browse, v.page!.page - 1)}>Previous 500</Button>
            <Button size="sm" variant="outline" disabled={v.page.page * v.page.page_rows >= v.page.total} onClick={() => onBrowse(browse, v.page!.page + 1)}>Next 500</Button>
          </div>
          <div className="max-h-80 overflow-auto">
            <table className="border-collapse">
              <thead><tr>{v.page.columns.map((c) => <th key={c} className="px-1 text-left">{c}</th>)}</tr></thead>
              <tbody>
                {v.page.rows.map((r, i) => (
                  <tr key={i} className="border-t align-top">{r.map((x, k) => <td key={k} className="max-w-xs break-all px-1"><Raw value={x} /></td>)}</tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}

/** A value as stored: a blob is its length and the first 64 bytes in hex, never decoded. */
export function Raw({ value }: { value: RawValue }) {
  if (value === null) return <span className="text-muted-foreground">NULL</span>
  if (typeof value === "object") {
    return <span>{value.blob_bytes.toLocaleString("en-US")} bytes{value.blob_bytes ? `: ${value.hex_preview}${value.preview_complete ? "" : " …"}` : ""}</span>
  }
  return <span>{String(value)}</span>
}
