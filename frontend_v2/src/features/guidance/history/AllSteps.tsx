import { useMemo, useState } from "react"
import { useInfiniteQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { AddToTheoryDialog } from "@/features/theory/AddToTheory"
import { historyAPI, stepsKey, type Step } from "../api"
import { when } from "./time-words"
import { useHistory } from "./recorder"
import { trailGroup } from "./trail"

const PAGE = 50

/**
 * Every step in this case, newest first, searchable by name (lx-guide H, K, L). Tick a run of steps to add them to a
 * theory as the trail that led to a finding. Clear removes this person's history for the case; trails already in a
 * theory keep their steps.
 */
export function AllStepsDialog({ caseId, onClose, onOpen }: { caseId: string; onClose: () => void; onOpen: (s: Step) => void }) {
  const qc = useQueryClient()
  const [q, setQ] = useState("")
  const [picked, setPicked] = useState<Record<string, Step>>({})
  const [adding, setAdding] = useState(false)
  const [confirmClear, setConfirmClear] = useState(false)
  const list = useInfiniteQuery({
    queryKey: [...stepsKey(caseId), "all", q.trim()],
    queryFn: ({ pageParam }) => historyAPI.list(caseId, { limit: PAGE, offset: pageParam, q }),
    initialPageParam: 0,
    getNextPageParam: (last, pages) => {
      const shown = pages.reduce((n, p) => n + p.steps.length, 0)
      return shown < last.total ? shown : undefined
    },
  })
  const steps = useMemo(() => list.data?.pages.flatMap((p) => p.steps) ?? [], [list.data])
  const total = list.data?.pages[0]?.total ?? 0
  const keepDays = list.data?.pages[0]?.keep_days ?? 90
  const chosen = Object.values(picked)
  const clear = useMutation({
    mutationFn: () => historyAPI.clear(caseId),
    onSuccess: () => {
      setPicked({})
      setConfirmClear(false)
      useHistory.getState().setCurrent(null)
      useHistory.getState().setLast(null)
      void qc.invalidateQueries({ queryKey: stepsKey(caseId) })
    },
  })
  // shift-click ticks every step between the last ticked one and this one: a run
  const [anchor, setAnchor] = useState<number | null>(null)
  const toggle = (i: number, shift: boolean) => {
    const step = steps[i]
    setPicked((p) => {
      const next = { ...p }
      if (shift && anchor !== null) {
        const [a, b] = anchor < i ? [anchor, i] : [i, anchor]
        for (const s of steps.slice(a, b + 1)) next[s.id] = s
      } else if (next[step.id]) delete next[step.id]
      else next[step.id] = step
      return next
    })
    setAnchor(i)
  }
  return (
    <Dialog open onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>All your steps in this case</DialogTitle>
          <DialogDescription>
            Only you see these. They are kept {keepDays} days. Click a step to return to it; tick a run of steps (Shift-click
            ticks every step between two) to add it to a theory.
          </DialogDescription>
        </DialogHeader>
        <Input placeholder="Search your steps, e.g. BBVA or Graph" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search your steps" />
        <p className="text-xs text-muted-foreground" role="status">
          {list.isLoading ? "Reading your steps…" : `Showing ${steps.length.toLocaleString("en-US")} of ${total.toLocaleString("en-US")} steps${q.trim() ? ` matching "${q.trim()}"` : ""}.`}
        </p>
        {list.isError && <p role="alert" className="text-sm">Your steps could not be read. Try again in a moment.</p>}
        <ol className="max-h-[50vh] overflow-y-auto rounded border border-border">
          {steps.map((s, i) => (
            <li key={s.id} className="flex items-center gap-2 border-b border-border px-2 py-1.5 text-sm last:border-b-0">
              <input
                type="checkbox"
                aria-label={`Choose ${s.name}`}
                checked={!!picked[s.id]}
                onChange={() => undefined}
                onClick={(e) => toggle(i, e.shiftKey)}
              />
              <button type="button" className="min-w-0 flex-1 truncate text-left hover:underline" onClick={() => onOpen(s)}>
                {s.name}
              </button>
              <span className="shrink-0 text-xs text-muted-foreground">{when(s.at)}</span>
            </li>
          ))}
        </ol>
        <div className="flex flex-wrap items-center gap-2">
          {list.hasNextPage && (
            <Button size="sm" variant="outline" disabled={list.isFetchingNextPage} onClick={() => void list.fetchNextPage()}>
              {list.isFetchingNextPage ? "Reading…" : `Show ${Math.min(PAGE, total - steps.length)} more`}
            </Button>
          )}
          <span className="flex-1" />
          {confirmClear ? (
            <>
              <span className="text-xs">Clear all {total.toLocaleString("en-US")} steps in this case?</span>
              <Button size="sm" variant="danger" disabled={clear.isPending} onClick={() => clear.mutate()}>
                Clear them
              </Button>
              <Button size="sm" variant="ghost" onClick={() => setConfirmClear(false)}>
                Keep them
              </Button>
            </>
          ) : (
            total > 0 && (
              <Button size="sm" variant="ghost" onClick={() => setConfirmClear(true)}>
                Clear my history
              </Button>
            )
          )}
          <Button size="sm" disabled={chosen.length === 0} onClick={() => setAdding(true)}>
            Add {chosen.length || ""} {chosen.length === 1 ? "step" : "steps"} to a theory…
          </Button>
        </div>
        {clear.error && <p role="alert" className="text-sm">The history was not cleared: {clear.error instanceof Error ? clear.error.message : "it failed"}.</p>}
      </DialogContent>
      {adding && (
        <AddToTheoryDialog
          caseId={caseId}
          surface="history"
          group={trailGroup(chosen)}
          onClose={() => setAdding(false)}
        />
      )}
    </Dialog>
  )
}
