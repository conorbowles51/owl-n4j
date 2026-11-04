import { useEffect, useRef, useState } from "react"
import { Button } from "@/components/ui/button"
import { StaleSnapshotError, failureText, streamFind, type StreamFilter } from "../api"

type Match = { day: string | null; offset: number; event_uid: string }

/**
 * Find in these results (03 section 3.1 rule 4, 07 section 4.8, test UX-2). The server searches the whole result,
 * not only the rows in view, and returns every match in list order with the true total, so "Match 3 of 214" counts
 * rows the virtual list has not loaded. The first Ctrl/Cmd+F opens this control; a second press, with the cursor in
 * it, passes to the browser's own find. Enter goes to the next match, Shift+Enter to the previous one.
 */
export function FindInResults({
  filter,
  snapshot,
  onGo,
  onQuery,
}: {
  filter: StreamFilter
  snapshot: string | undefined
  onGo: (m: Match) => void
  onQuery?: (q: string | null) => void
}) {
  const input = useRef<HTMLInputElement>(null)
  const [open, setOpen] = useState(false)
  const [text, setText] = useState("")
  const [result, setResult] = useState<{ q: string; snapshot: string; matches: Match[]; total: number } | null>(null)
  const [at, setAt] = useState(0)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      if (!(e.ctrlKey || e.metaKey) || e.altKey || (e.key !== "f" && e.key !== "F")) return
      if (document.activeElement === input.current) return // the second press: the browser's own find
      e.preventDefault()
      setOpen(true)
      window.setTimeout(() => input.current?.focus(), 0)
    }
    window.addEventListener("keydown", h)
    return () => window.removeEventListener("keydown", h)
  }, [])

  // a new result (filter or data changed) makes the matches stale: they are searched again on the next Enter
  const current = result && result.snapshot === snapshot ? result : null

  async function search(step: 1 | -1) {
    const q = text.trim()
    if (!q || !snapshot) return
    if (current && current.q === q) {
      if (!current.total) return
      const next = (at + step + current.total) % current.total
      setAt(next)
      onGo(current.matches[next])
      return
    }
    setBusy(true)
    setError(null)
    try {
      const r = await streamFind(filter, snapshot, q)
      setResult({ q, snapshot, matches: r.matches, total: r.total })
      setAt(0)
      onQuery?.(q)
      if (r.total) onGo(r.matches[0])
    } catch (e) {
      setResult(null)
      setError(e instanceof StaleSnapshotError ? "The list changed while searching. Press Enter to search again." : failureText(e, "The search could not be run."))
    } finally {
      setBusy(false)
    }
  }

  if (!open)
    return (
      <Button size="sm" variant="outline" onClick={() => { setOpen(true); window.setTimeout(() => input.current?.focus(), 0) }} title="Ctrl/Cmd+F">
        Find in these results
      </Button>
    )
  return (
    <span role="search" aria-label="Find in these results" className="flex flex-wrap items-center gap-2 text-xs">
      <input
        ref={input}
        aria-label="Find in these results"
        className="w-48 rounded border bg-background px-2 py-1"
        value={text}
        placeholder="Find in these results"
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            e.preventDefault()
            void search(e.shiftKey ? -1 : 1)
          } else if (e.key === "Escape") {
            setOpen(false)
            setResult(null)
            onQuery?.(null)
          }
          e.stopPropagation() // j, k and the list's other keys are typing here
        }}
      />
      <Button size="sm" variant="ghost" disabled={!current?.total || busy} onClick={() => void search(-1)} aria-label="Previous match">
        Previous
      </Button>
      <Button size="sm" variant="ghost" disabled={busy || !text.trim()} onClick={() => void search(1)} aria-label="Next match">
        Next
      </Button>
      <span role="status">
        {busy ? "Searching the whole result" : current ? (current.total ? `Match ${(at + 1).toLocaleString("en-US")} of ${current.total.toLocaleString("en-US")}` : "No match in these results") : ""}
      </span>
      {error && <span role="alert">{error}</span>}
      <Button size="sm" variant="ghost" onClick={() => { setOpen(false); setResult(null); onQuery?.(null) }}>
        Close
      </Button>
    </span>
  )
}
