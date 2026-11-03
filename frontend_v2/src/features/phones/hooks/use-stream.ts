import { useCallback, useEffect, useLayoutEffect, useMemo, useReducer, useRef, useState } from "react"
import { failureText, StaleSnapshotError, streamIndex, streamLocate, streamWindow, type StreamFilter } from "../api"
import type { StreamIndex, StreamRow, StreamWindow } from "../schemas"

/**
 * Index then windows (03 section 3.1; D-1):
 *
 * - The index gives the exact total, per-day counts and the undated count; the list is sized to the whole result
 *   from the first paint, so the scrollbar is the whole result. There is no "Load more" anywhere.
 * - At or under ``full_load_rows`` (5,000, D-2) every window is fetched at once after the index, in requests of
 *   1,000 rows, so the whole result is in memory. Above it, windows load as they come into view, two ahead and one
 *   behind.
 * - A window that fails is retried once after 2 seconds; if it fails again its rows show "These messages could not
 *   be loaded. Retry." in place and the rest of the list keeps working (rule 8).
 * - A stale snapshot (409) re-reads the index and keeps the focused event in view (rule 3, C-9).
 */

export const WINDOW = 200
export const FULL_WINDOW = 1000
export const STALE_NOTICE = "New data arrived while you were reading. The list has been refreshed and kept your place."
export const WINDOW_FAILED = "These messages could not be loaded. Retry."
export const INDEX_FAILED = "The message list could not be loaded."

export interface Segment {
  day: string | null
  header: string
  zoneLabel: string | null
  count: number
  /** Position of this segment's header in the virtual item list. */
  start: number
}

export type StreamItem =
  | { type: "header"; segment: number }
  | { type: "row"; segment: number; offset: number; row: StreamRow | null; state: "loaded" | "loading" | "failed"; windowKey: string }

export function buildSegments(index: StreamIndex): Segment[] {
  const segs: Segment[] = []
  let pos = 0
  const undated = index.no_time_count
    ? [{ day: null, header: "No time recorded", zoneLabel: null, count: index.no_time_count }]
    : []
  const dated = index.items.map((d) => ({ day: d.day, header: d.header, zoneLabel: d.zone_label, count: d.count }))
  const ordered = index.no_time_position === "first" ? [...undated, ...dated] : [...dated, ...undated]
  for (const s of ordered) {
    segs.push({ ...s, start: pos })
    pos += s.count + 1
  }
  return segs
}

export function itemCount(segs: Segment[]): number {
  const last = segs[segs.length - 1]
  return last ? last.start + last.count + 1 : 0
}

/** The segment holding virtual position ``i`` (binary search). */
export function segmentAt(segs: Segment[], i: number): number {
  let lo = 0
  let hi = segs.length - 1
  while (lo < hi) {
    const mid = (lo + hi + 1) >> 1
    if (segs[mid].start <= i) lo = mid
    else hi = mid - 1
  }
  return lo
}

type WinState = { state: "loading" | "failed" | "loaded"; tries: number }

export interface UseStream {
  status: "idle" | "loading" | "ready" | "error"
  error: string | null
  index: StreamIndex | null
  segments: Segment[]
  count: number
  total: number
  notice: string | null
  item: (i: number) => StreamItem
  ensure: (from: number, to: number) => void
  retry: (windowKey: string) => void
  reload: () => void
  positionOf: (eventUid: string) => number | null
  /** Every row of the result, fetching windows not yet loaded (for Copy and Select all, 3.7). */
  allRows: (onProgress?: (done: number, total: number) => void) => Promise<StreamRow[]>
  setFocused: (eventUid: string | null) => void
}

/** Where the index and windows come from: Conversations' streams by default; the Timeline lens passes its own
 * (03 section 9.3) so the same list, copy and badges serve both. */
export interface StreamSource {
  index: (f: StreamFilter) => Promise<StreamIndex>
  window: (f: StreamFilter, snapshot: string, day: string | null, offset: number, limit: number) => Promise<StreamWindow>
  locate: (f: StreamFilter, snapshot: string, eventUid: string) => Promise<{ day: string | null; offset: number }>
}
const STREAMS: StreamSource = { index: (f) => streamIndex(f), window: (f, s, d, o, l) => streamWindow(f, s, d, o, l), locate: streamLocate }

export function useStream(filter: StreamFilter | null, deps: { onStaleRestore?: (position: number) => void; source?: StreamSource } = {}): UseStream {
  const [index, setIndex] = useState<StreamIndex | null>(null)
  const [status, setStatus] = useState<UseStream["status"]>("idle")
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [, bump] = useReducer((n: number) => n + 1, 0)
  const rows = useRef(new Map<string, StreamRow[]>()) // key `${seg}|${start}`
  const wins = useRef(new Map<string, WinState>())
  const focused = useRef<string | null>(null)
  const generation = useRef(0)
  // True while an index request runs: windows are never asked for with the previous index's snapshot and the new
  // filter (that always answers 409 and would restart the index request, review of 03-2).
  const indexLoading = useRef(false)
  const filterKey = filter ? JSON.stringify(filter) : ""
  const segments = useMemo(() => (index ? buildSegments(index) : []), [index])
  const count = itemCount(segments)
  const windowSize = index && index.counts.events <= index.full_load_rows ? FULL_WINDOW : WINDOW
  const filterRef = useRef(filter)
  const fetchRef = useRef<((seg: number, start: number) => Promise<void>) | null>(null)
  const restoreRef = useRef(deps.onStaleRestore)
  const sourceRef = useRef(deps.source ?? STREAMS)
  // Kept in step before the load effect below runs (effects run in order).
  useLayoutEffect(() => {
    filterRef.current = filter
    restoreRef.current = deps.onStaleRestore
    sourceRef.current = deps.source ?? STREAMS
  })

  const loadIndex = useCallback(async (stale: boolean) => {
    const f = filterRef.current
    if (!f) return
    const gen = ++generation.current
    indexLoading.current = true
    rows.current = new Map()
    wins.current = new Map()
    setStatus("loading")
    setError(null)
    try {
      const idx = await sourceRef.current.index(f)
      if (gen !== generation.current) return
      indexLoading.current = false
      setIndex(idx)
      setStatus("ready")
      if (stale) {
        setNotice(STALE_NOTICE)
        const uid = focused.current
        if (uid) {
          try {
            const loc = await sourceRef.current.locate(f, idx.snapshot, uid)
            const segs = buildSegments(idx)
            const seg = segs.find((s) => s.day === loc.day)
            if (seg && restoreRef.current) restoreRef.current(seg.start + 1 + loc.offset)
          } catch {
            /* the focused event left the result; the list stays at its scroll position */
          }
        }
      }
    } catch (e) {
      if (gen !== generation.current) return
      indexLoading.current = false
      setStatus("error")
      setError(failureText(e, INDEX_FAILED))
    }
  }, [])

  // An unmounted list asks for nothing more: its retry timers and late replies end with its generation.
  useEffect(
    () => () => {
      generation.current++
    },
    [],
  )

  useEffect(() => {
    if (!filterKey) return
    setNotice(null)
    void loadIndex(false)
  }, [filterKey, loadIndex])

  const fetchWindow = useCallback(
    async (seg: number, start: number) => {
      const idx = index
      const f = filterRef.current
      if (!idx || !f || indexLoading.current) return
      const key = `${seg}|${start}`
      const prev = wins.current.get(key)
      if (prev && (prev.state === "loading" || prev.state === "loaded")) return
      const gen = generation.current
      const tries = (prev?.tries ?? 0) + 1
      wins.current.set(key, { state: "loading", tries })
      bump()
      const s = buildSegments(idx)[seg]
      try {
        const w = await sourceRef.current.window(f, idx.snapshot, s.day, start, Math.min(windowSize, s.count - start))
        if (gen !== generation.current) return
        rows.current.set(key, w.items)
        wins.current.set(key, { state: "loaded", tries })
        bump()
      } catch (e) {
        if (gen !== generation.current) return
        if (e instanceof StaleSnapshotError) {
          void loadIndex(true)
          return
        }
        wins.current.set(key, { state: "failed", tries })
        bump()
        if (tries === 1) {
          setTimeout(() => {
            if (gen === generation.current) void fetchRef.current?.(seg, start)
          }, 2000)
        }
      }
    },
    [index, windowSize, loadIndex],
  )

  useEffect(() => {
    fetchRef.current = fetchWindow
  }, [fetchWindow])

  // Full load (rule 4): every window, sequentially, right after the index.
  useEffect(() => {
    if (!index || index.counts.events > index.full_load_rows) return
    let cancelled = false
    const gen = generation.current
    void (async () => {
      const segs = buildSegments(index)
      for (let si = 0; si < segs.length; si++) {
        for (let start = 0; start < segs[si].count; start += FULL_WINDOW) {
          if (cancelled || gen !== generation.current) return
          await fetchWindow(si, start)
        }
      }
    })()
    return () => {
      cancelled = true
    }
  }, [index, fetchWindow])

  const item = useCallback(
    (i: number): StreamItem => {
      const si = segmentAt(segments, i)
      const s = segments[si]
      if (!s || i === s.start) return { type: "header", segment: si }
      const offset = i - s.start - 1
      const start = Math.floor(offset / windowSize) * windowSize
      const key = `${si}|${start}`
      const got = rows.current.get(key)
      const ws = wins.current.get(key)
      const row = got ? got[offset - start] ?? null : null
      return { type: "row", segment: si, offset, row, state: row ? "loaded" : ws?.state === "failed" ? "failed" : "loading", windowKey: key }
    },
    [segments, windowSize],
  )

  const ensure = useCallback(
    (from: number, to: number) => {
      if (!segments.length) return
      const span = Math.max(1, to - from)
      const lo = Math.max(0, from - windowSize)
      const hi = Math.min(count - 1, to + Math.max(span, windowSize) * 2)
      const wanted = new Set<string>()
      for (let i = lo; i <= hi; i++) {
        const it = item(i)
        if (it.type === "row" && it.state !== "loaded") wanted.add(it.windowKey)
        if (wanted.size > 8) break
      }
      for (const key of wanted) {
        const ws = wins.current.get(key)
        if (ws?.state === "failed") continue // shown with Retry; the automatic retry already ran
        const [seg, start] = key.split("|").map(Number)
        void fetchWindow(seg, start)
      }
    },
    [segments, count, item, fetchWindow, windowSize],
  )

  const retry = useCallback(
    (key: string) => {
      const [seg, start] = key.split("|").map(Number)
      wins.current.set(key, { state: "failed", tries: 1 })
      void fetchWindow(seg, start)
    },
    [fetchWindow],
  )

  const positionOf = useCallback(
    (uid: string) => {
      for (const [key, list] of rows.current) {
        const k = list.findIndex((r) => r.event_uid === uid)
        if (k >= 0) {
          const [seg, start] = key.split("|").map(Number)
          return segments[seg].start + 1 + start + k
        }
      }
      return null
    },
    [segments],
  )

  const allRows = useCallback(
    async (onProgress?: (done: number, total: number) => void) => {
      const idx = index
      const f = filterRef.current
      if (!idx || !f || indexLoading.current) throw new Error("The list is still loading.")
      const segs = buildSegments(idx)
      const out: StreamRow[] = []
      for (let si = 0; si < segs.length; si++) {
        for (let start = 0; start < segs[si].count; start += windowSize) {
          let got = rows.current.get(`${si}|${start}`)
          if (!got) {
            let w
            try {
              w = await sourceRef.current.window(f, idx.snapshot, segs[si].day, start, Math.min(windowSize, segs[si].count - start))
            } catch (e) {
              if (e instanceof StaleSnapshotError) void loadIndex(true)
              throw e
            }
            got = w.items
            rows.current.set(`${si}|${start}`, got)
            wins.current.set(`${si}|${start}`, { state: "loaded", tries: 1 })
          }
          out.push(...got)
          onProgress?.(out.length, idx.counts.events)
        }
      }
      bump()
      return out
    },
    [index, windowSize, loadIndex],
  )

  return {
    status,
    error,
    index,
    segments,
    count,
    total: index?.counts.events ?? 0,
    notice,
    item,
    ensure,
    retry,
    reload: () => void loadIndex(false),
    positionOf,
    allRows,
    setFocused: (uid) => {
      focused.current = uid
    },
  }
}
