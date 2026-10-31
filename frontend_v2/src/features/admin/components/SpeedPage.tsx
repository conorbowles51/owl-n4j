import { useState } from "react"
import { Gauge, RefreshCw } from "lucide-react"
import { useQuery } from "@tanstack/react-query"
import { Button } from "@/components/ui/button"
import { ScrollArea } from "@/components/ui/scroll-area"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { fetchAPI } from "@/lib/api-client"
import { describePageCache, formatDuration, type PageCacheStats, type SpeedSummary } from "../speed"

const ALL = "all"

function formatBytes(bytes: number) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`
  return `${(bytes / 1024 / 1024 / 1024).toFixed(2)} GB`
}

function what(row: { kind: string; method: string; route: string }) {
  if (row.kind === "page")
    return `${row.method === "LOAD" ? "Opened" : row.method === "LEFT" ? "Left before shown:" : "Switched to"} ${row.route}`
  return `${row.method} ${row.route}`
}

/** How long requests and Financial page views take. Admins only (server enforced). */
/** How a slow request's Financial view was served: a kept copy, the previous copy while it is recomputed, or computed now. */
function cacheLabel(cache: string): string {
  if (cache === "hit" || cache === "saved") return "kept copy"
  if (cache === "updating") return "previous copy, updating"
  return "computed"
}

export function SpeedPage() {
  const [days, setDays] = useState("1")
  const [caseId, setCaseId] = useState(ALL)
  const [kind, setKind] = useState(ALL)

  const query = useQuery({
    queryKey: ["admin", "speed", days, caseId, kind],
    queryFn: () => {
      const qs = new URLSearchParams({ days })
      if (caseId !== ALL) qs.set("case_id", caseId)
      if (kind !== ALL) qs.set("kind", kind)
      return fetchAPI<SpeedSummary>(`/api/request-speed/summary?${qs}`)
    },
    placeholderData: (previous) => previous, // keep the case list and table while a filter reloads
  })
  const data = query.data
  const pageCache = useQuery({
    queryKey: ["admin", "speed", "page-cache"],
    queryFn: () => fetchAPI<PageCacheStats>("/api/request-speed/page-cache"),
  })
  const caseTitle = (id: string | null, title?: string | null) =>
    title || (id && data?.cases.find((item) => item.id === id)?.title) || (id ? id.slice(0, 8) : "")

  return (
    <div className="flex h-full flex-col bg-background">
      <div className="flex flex-wrap items-center gap-2 border-b border-border bg-card px-4 py-2">
        <Gauge className="size-4 text-amber-500" />
        <span className="font-display text-sm font-semibold">Speed</span>
        <div className="flex-1" />
        <Select value={days} onValueChange={setDays}>
          <SelectTrigger className="w-40" aria-label="Period">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="1">Last 24 hours</SelectItem>
            <SelectItem value="7">Last 7 days</SelectItem>
          </SelectContent>
        </Select>
        <Select value={kind} onValueChange={setKind}>
          <SelectTrigger className="w-48" aria-label="What">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>Pages and requests</SelectItem>
            <SelectItem value="page">Pages as people see them</SelectItem>
            <SelectItem value="api">Server requests</SelectItem>
          </SelectContent>
        </Select>
        <Select value={caseId} onValueChange={setCaseId}>
          <SelectTrigger className="w-56" aria-label="Case">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>All cases</SelectItem>
            {(data?.cases ?? []).map((item) => (
              <SelectItem key={item.id} value={item.id}>
                {item.title || item.id.slice(0, 8)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Button variant="ghost" size="sm" aria-label="Refresh" onClick={() => void query.refetch()}>
          <RefreshCw className="size-3.5" />
        </Button>
      </div>
      <p className="border-b border-border px-4 py-2 text-xs text-muted-foreground">
        How long things take, slowest first. "Typical" is the time half of them beat; "Slow end" is the time
        19 in 20 beat; "Slowest" is the single longest. Pages are timed in the browser, from opening a
        Financial view to its data being on screen; "Left before shown" is how long someone waited
        before leaving a view whose data had not arrived. Server requests are timed from arrival to the last byte
        sent. Recorded since 28 Oct 2026; totals are saved about every 15 seconds.
      </p>
      <p className="border-b border-border px-4 py-2 text-xs text-muted-foreground" aria-label="Stored page images">
        {pageCache.data
          ? describePageCache(pageCache.data, formatBytes)
          : pageCache.isError
            ? "Stored page images could not be read."
            : "Stored page images: loading…"}
      </p>
      <ScrollArea className="flex-1">
        <table className="w-full text-left text-xs">
          <thead className="sticky top-0 bg-card text-muted-foreground">
            <tr>
              <th className="px-3 py-2">What</th>
              <th className="px-3 py-2 text-right">Typical</th>
              <th className="px-3 py-2 text-right">Slow end</th>
              <th className="px-3 py-2 text-right">Slowest</th>
              <th className="px-3 py-2 text-right">How many</th>
              <th className="px-3 py-2 text-right">Failed</th>
              <th className="px-3 py-2 text-right">Data sent</th>
            </tr>
          </thead>
          <tbody>
            {(data?.routes ?? []).map((row) => (
              <tr key={`${row.kind} ${row.method} ${row.route}`} className="border-t border-border">
                <td className="px-3 py-1.5 font-mono">{what(row)}</td>
                <td className="px-3 py-1.5 text-right">{formatDuration(row.p50_ms)}</td>
                <td className="px-3 py-1.5 text-right">{formatDuration(row.p95_ms)}</td>
                <td className="px-3 py-1.5 text-right">{formatDuration(row.max_ms)}</td>
                <td className="px-3 py-1.5 text-right">{row.count.toLocaleString()}</td>
                <td className="px-3 py-1.5 text-right">{row.errors ? row.errors.toLocaleString() : ""}</td>
                <td className="px-3 py-1.5 text-right">{row.kind === "api" ? formatBytes(row.bytes) : ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {!data?.routes.length && (
          <p className="py-8 text-center text-muted-foreground">
            {query.isLoading ? "Loading…" : query.isError ? "Speed could not be loaded." : "Nothing recorded in this period."}
          </p>
        )}
        <h2 className="border-t border-border px-4 pb-1 pt-4 text-sm font-semibold">
          Slow requests (over {data?.slow_row_seconds ?? 2} s, kept {data?.slow_keep_days ?? 30} days)
        </h2>
        <table className="w-full text-left text-xs">
          <thead className="text-muted-foreground">
            <tr>
              <th className="px-3 py-2">When</th>
              <th className="px-3 py-2">What</th>
              <th className="px-3 py-2">Case</th>
              <th className="px-3 py-2">Who</th>
              <th className="px-3 py-2 text-right">Took</th>
              <th className="px-3 py-2 text-right" title="Time spent in the database inside this request">Database</th>
              <th className="px-3 py-2 text-right" title="The longest its server worker was held that minute (it could not start other requests)">Worker held</th>
              <th className="px-3 py-2 text-right" title="Share of that minute in which work on the machine waited for a CPU">Machine busy</th>
              <th className="px-3 py-2 text-right" title="CPU cores used by the automated jobs that minute (of 6)">Jobs CPU</th>
              <th className="px-3 py-2 text-right">Result</th>
            </tr>
          </thead>
          <tbody>
            {(data?.slow ?? []).map((row, index) => (
              <tr key={`${row.at} ${index}`} className="border-t border-border">
                <td className="whitespace-nowrap px-3 py-1.5">
                  {new Date(row.at).toLocaleString(undefined, { timeZoneName: "short" })}
                </td>
                <td className="px-3 py-1.5 font-mono">{what(row)}</td>
                <td className="px-3 py-1.5">{caseTitle(row.case_id, row.case_title)}</td>
                <td className="px-3 py-1.5">{row.user_name || ""}</td>
                <td className="px-3 py-1.5 text-right">{formatDuration(row.duration_ms)}</td>
                <td className="px-3 py-1.5 text-right">
                  {row.pg_ms == null ? "" : formatDuration(row.pg_ms)}
                  {row.cache ? ` (${cacheLabel(row.cache)})` : ""}
                </td>
                <td className="px-3 py-1.5 text-right">{row.loop_lag_max_ms == null ? "" : formatDuration(row.loop_lag_max_ms)}</td>
                <td className="px-3 py-1.5 text-right">{row.host_cpu_pressure == null ? "" : `${Math.round(row.host_cpu_pressure)}%`}</td>
                <td className="px-3 py-1.5 text-right">{row.fleet_cores == null ? "" : row.fleet_cores.toFixed(1)}</td>
                <td className="px-3 py-1.5 text-right">
                  {row.kind === "page" ? "" : row.status && row.status >= 400 ? `failed (${row.status})` : "ok"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {data && !data.slow.length && (
          <p className="py-6 text-center text-muted-foreground">No slow requests in this period.</p>
        )}
      </ScrollArea>
    </div>
  )
}
