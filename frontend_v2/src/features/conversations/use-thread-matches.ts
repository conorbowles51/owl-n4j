import { useQuery } from "@tanstack/react-query"
import { streamIndex, streamWindow, type StreamFilter } from "@/features/phones/api"

/**
 * The messages of the open thread that a search matched (03 S-8), in list order: the same filter with the search's
 * text, read in full (a thread's matches, 1,000 per request). The list itself stays unfiltered; these are only
 * marked and stepped through.
 */
export function useThreadMatches(filter: StreamFilter | null, query: string, exact: boolean) {
  return useQuery({
    queryKey: ["thread-matches", filter, query, exact],
    enabled: !!filter && !!query.trim(),
    staleTime: 60_000,
    retry: false,
    queryFn: async ({ signal }) => {
      const f: StreamFilter = { ...filter!, text: { query, exact_characters: exact } }
      const idx = await streamIndex(f, signal)
      const days: { day: string | null; count: number }[] = idx.items.map((d) => ({ day: d.day, count: d.count }))
      if (idx.no_time_count) days.push({ day: null, count: idx.no_time_count })
      const events: string[] = []
      for (const d of days)
        for (let off = 0; off < d.count; off += 1000) {
          const w = await streamWindow(f, idx.snapshot, d.day, off, Math.min(1000, d.count - off), signal)
          events.push(...w.items.map((r) => r.event_uid))
        }
      return { total: idx.counts.events ?? events.length, events }
    },
  })
}
