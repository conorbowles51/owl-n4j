import { useQuery } from "@tanstack/react-query"
import { MAX_TOGETHER_PHONES, meetingWhen, overlapsQuery } from "./phone-together"

/** Timeline: one band of shared moments over the lens's span, a block for each time the chosen phones were together. */
export function TogetherBand({ caseId, phoneIds, from, to }: { caseId: string; phoneIds: string[]; from?: string | null; to?: string | null }) {
  const q = useQuery({ ...overlapsQuery(caseId, phoneIds, from, to), enabled: phoneIds.length >= 2 && phoneIds.length <= MAX_TOGETHER_PHONES })
  const ms = q.data?.together ?? []
  if (!q.data) return <p role="status" className="px-3 py-1 text-sm" data-testid="together-band">{q.isError ? "Shared moments could not be read. Try again." : phoneIds.length < 2 ? "Switch on at least two phones to see shared moments." : "Reading shared moments"}</p>
  if (!ms.length) return <p role="status" className="px-3 py-1 text-sm" data-testid="together-band">Shared moments: {q.data.message}</p>
  const lo = Math.min(...ms.map((m) => Date.parse(m.start))), hi = Math.max(...ms.map((m) => Date.parse(m.end)))
  const span = Math.max(1, hi - lo)
  return (
    <div className="px-3 py-1 text-sm" data-testid="together-band">
      <div>Shared moments: {ms.length.toLocaleString("en-US")} {ms.length === 1 ? "time" : "times"} the chosen phones were in the same place, {meetingWhen({ start: new Date(lo).toISOString(), end: new Date(hi).toISOString() })}</div>
      <div className="relative my-1 h-6 rounded bg-muted" role="img" aria-label={`${ms.length} shared moments`}>
        {ms.map((m) => (
          <span key={m.id} title={meetingWhen(m)} className="absolute top-0.5 h-5 rounded-sm bg-[#6a2c91]/85"
            style={{ left: `${((Date.parse(m.start) - lo) / span) * 100}%`, width: `max(4px, ${((Date.parse(m.end) - Date.parse(m.start)) / span) * 100}%)` }} />
        ))}
      </div>
    </div>
  )
}
