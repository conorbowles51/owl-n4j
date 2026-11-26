import { useQueries } from "@tanstack/react-query"
import { Link } from "react-router-dom"
import { fetchAPI } from "@/lib/api-client"
import type { ElsewhereItem } from "../home/HomeRecordPanel"
import { citationHref } from "../home/home-words"
import type { MentionDetail } from "./api"

/**
 * What the rest of the case says about the selected mention, from the case's "elsewhere" service: one request per
 * source so each fills in as it arrives. Its relations are its own rules; the mention's outcome above stays the
 * mention checks' own. A possible match is labelled so and is never counted as agreement.
 */

type Item = ElsewhereItem
interface Part { source: string; label: string; state: string; searched: string; items: Item[] }

const PARTS = ["financial", "documents", "timeline", "phones"] as const

export function Elsewhere({ caseId, d }: { caseId: string; d: MentionDetail }) {
  const body = {
    text: d.phrase,
    record_uids: [d.record_uid],
    period: { start: d.window.start, end: d.window.end },
    amounts: d.amounts_minor.map((minor) => ({ minor, currency: "USD" })),
    places: d.where?.located && d.where.lat != null ? [{ name: d.where.name, lat: d.where.lat, lon: d.where.lon, radius_m: d.where.radius_m }] : [],
  }
  const parts = useQueries({
    queries: PARTS.map((p) => ({
      queryKey: ["mention-elsewhere", caseId, d.id, p],
      queryFn: () => fetchAPI<{ parts: Part[] }>(`/api/cases/${encodeURIComponent(caseId)}/elsewhere/statement?part=${p}`, { method: "POST", body, read: true }),
      staleTime: 60_000,
      retry: false,
    })),
  })
  const shown = parts.flatMap((q) => q.data?.parts ?? [])
  const items = shown.flatMap((p) => p.items.filter((i) => i.relation !== "nothing_found").map((i) => ({ ...i, source: p.label })))
  const loading = parts.some((q) => q.isLoading)
  const failed = parts.filter((q) => q.isError).length + shown.filter((p) => p.state !== "done").length
  return (
    <section aria-label="Elsewhere in the case" className="flex flex-col gap-1.5">
      <h3 className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">Elsewhere in the case</h3>
      {items.length > 0 ? (
        <ul>
          {items.slice(0, 8).map((i, k) => {
            const to = i.citation ? citationHref(caseId, i.citation) : null
            return (
              <li key={k} className="border-t py-2 text-[13px] leading-snug">
                <span className="font-semibold">{i.source} · {i.relation_label}:</span> {i.text}
                {i.reason && <span className="block text-xs text-muted-foreground">{i.reason}</span>}
                {i.machine_label && <span className="block text-xs font-medium text-status-model">{i.machine_label}</span>}
                {i.citation && (to ? <Link to={to} className="mt-0.5 inline-block rounded border bg-muted px-1.5 font-mono text-[11px] no-underline hover:underline">{i.citation.label || "Open it"}</Link>
                  : <span className="mt-0.5 inline-block rounded border px-1.5 font-mono text-[11px]">{i.citation.label}</span>)}
              </li>
            )
          })}
          {items.length > 8 && <li className="border-t py-1.5 text-xs text-muted-foreground">and {items.length - 8} more</li>}
        </ul>
      ) : !loading && shown.length > 0 ? (
        <p className="text-xs text-muted-foreground">Nothing else in the case relates to it. {shown.map((p) => p.searched).filter(Boolean).join(" ")}</p>
      ) : null}
      {loading && <p className="text-xs text-muted-foreground">Looking through the rest of the case…</p>}
      {failed > 0 && <p className="text-xs text-muted-foreground">{failed} of the {PARTS.length} sources could not be searched just now; the checks above are complete without them.</p>}
    </section>
  )
}
