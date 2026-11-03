import { useQuery } from "@tanstack/react-query"
import { fetchAPI } from "@/lib/api-client"

/** Approach 2's clock offsets beside the incident window's times (05 sections 5.3.5 and 16). A reading about two
 * phones' clocks: no time is moved. */
interface Offsets {
  run: { id: string; finished_at: string | null; current: boolean } | null
  items: { phones: string[] | null; family: string | null; timestamp_class: string | null; offset_s: number | null; pairs: number | null; words: string | null }[]
}

export function ClockOffsets({ caseId }: { caseId: string }) {
  const q = useQuery({ queryKey: ["clock-offsets", caseId], enabled: !!caseId,
    queryFn: () => fetchAPI<Offsets>(`/api/phone-analysis/clock-offsets?case_id=${encodeURIComponent(caseId)}`) })
  if (!q.data) return null
  const { run, items } = q.data
  return (
    <section aria-label="Clock differences between phones" className="space-y-1 text-xs">
      {!run ? (
        <p>Messages across phones has not been run, so no difference between the phones' clocks is known; each time is shown as its phone recorded it.</p>
      ) : (
        <>
          <p>Differences between the phones' clocks, from the latest run of Messages across phones. They are readings about the clocks; no time here is moved.{!run.current && " The phones have changed since that run."}</p>
          {items.length === 0 ? <p>That run measured no clock difference between any two phones.</p> : (
            <ul className="list-disc pl-4">
              {items.map((o, i) => <li key={i}>{o.family ? `${o.family}: ` : ""}{o.words}</li>)}
            </ul>
          )}
        </>
      )}
    </section>
  )
}
