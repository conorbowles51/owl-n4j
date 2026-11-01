import { useQuery } from "@tanstack/react-query"
import { fetchAPI } from "@/lib/api-client"
import { formatDuration } from "../speed"

/** Journey names from the phone experience plan (07 section 3). */
export const JOURNEY_WORDS: Record<string, string> = {
  "J-1": "Add a phone and know it arrived whole",
  "J-2": "First look at a phone",
  "J-3": "Everything with one person, or between two",
  "J-4": "Read a conversation around a date",
  "J-5": "Reconstruct the window around a moment",
  "J-6": "Search everything and read the hit in context",
  "J-7": "Who is who: link identities and set owners",
  "J-8": "Check the system's readings",
  "J-9": "Test a statement against the phones",
  "J-10": "Where was the phone, and were two people together",
  "J-11": "Find deleted or concealed material",
  "J-12": "Build the case while reading",
  "J-13": "Share the review and know what is left",
  "J-14": "Export for counsel",
  "J-15": "Resume and hand over",
  "J-16": "Compare phones for a person or a pair",
  "J-17": "Explain a finding",
}

export type UxFunnels = {
  days: number
  journeys: { journey: string; started: number; completed: number; abandoned: number; median_ms: number | null; steps: { step: number; reached: number }[] }[]
  waits: { over_2s: number; over_2s_without_panel: number; left_before_data: number }
  collect: { actions: number; records: number }
  review_median_ms: Record<string, number>
}

export function funnelLine(j: UxFunnels["journeys"][number]): string {
  const steps = j.steps.map((s) => `step ${s.step}: ${s.reached.toLocaleString("en-US")}`).join(" · ")
  return steps || "no steps recorded"
}

/** Phone screen funnels (07 10.2): counts and times only, from Loupe's own records. Admins only (server enforced). */
export function PhoneJourneys({ days }: { days: string }) {
  const d = Math.min(90, Math.max(1, Number(days) || 1))
  const query = useQuery({
    queryKey: ["admin", "speed", "ux-funnels", d],
    queryFn: () => fetchAPI<UxFunnels>(`/api/request-speed/ux-funnels?days=${d}`),
  })
  // Only a well-formed answer is shown; anything else reads as "could not be loaded".
  const data = query.data && Array.isArray(query.data.journeys) && query.data.waits && query.data.collect ? query.data : undefined
  const failed = query.isError || (query.data !== undefined && data === undefined)
  return (
    <section aria-labelledby="phone-journeys-heading">
      <h2 id="phone-journeys-heading" className="border-t border-border px-4 pb-1 pt-4 text-sm font-semibold">
        Phone journeys (last {d} {d === 1 ? "day" : "days"})
      </h2>
      <p className="px-4 pb-2 text-xs text-muted-foreground">
        How far people get through each phone task, counted on the phone screens. Only counts and times are recorded,
        never names, numbers, message text or searches.
      </p>
      <table className="w-full text-left text-xs">
        <thead className="text-muted-foreground">
          <tr>
            <th className="px-3 py-2">Task</th>
            <th className="px-3 py-2 text-right">Started</th>
            <th className="px-3 py-2 text-right">Finished</th>
            <th className="px-3 py-2 text-right">Gave up</th>
            <th className="px-3 py-2 text-right">Typical time to finish</th>
            <th className="px-3 py-2">Reached</th>
          </tr>
        </thead>
        <tbody>
          {(data?.journeys ?? []).map((j) => (
            <tr key={j.journey} className="border-t border-border">
              <td className="px-3 py-1.5">{JOURNEY_WORDS[j.journey] ?? j.journey}</td>
              <td className="px-3 py-1.5 text-right">{j.started.toLocaleString("en-US")}</td>
              <td className="px-3 py-1.5 text-right">{j.completed.toLocaleString("en-US")}</td>
              <td className="px-3 py-1.5 text-right">{j.abandoned.toLocaleString("en-US")}</td>
              <td className="px-3 py-1.5 text-right">{j.median_ms == null ? "" : formatDuration(j.median_ms)}</td>
              <td className="px-3 py-1.5">{funnelLine(j)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {!data?.journeys.length && (
        <p className="py-6 text-center text-muted-foreground">
          {query.isLoading ? "Loading…" : failed ? "Phone journeys could not be loaded." : "No phone tasks recorded in this period."}
        </p>
      )}
      {data && (
        <p className="px-4 pb-3 text-xs text-muted-foreground" aria-label="Phone waits and collecting">
          Waits over 2 s: {data.waits.over_2s.toLocaleString("en-US")}, of which {data.waits.over_2s_without_panel.toLocaleString("en-US")} showed
          no progress panel. Left before the data arrived: {data.waits.left_before_data.toLocaleString("en-US")}. Added to the case:{" "}
          {data.collect.actions.toLocaleString("en-US")} times, {data.collect.records.toLocaleString("en-US")} records.
          {Object.entries(data.review_median_ms ?? {}).map(([q, ms]) => ` Typical time per ${q.replace(/-/g, " ")} decision: ${formatDuration(ms)}.`).join("")}
        </p>
      )}
    </section>
  )
}
