import { useState } from "react"
import { useProductionActions, useProductionNumbers, type NumberItem } from "../production-numbers.api"

/** The file's production numbers, each with what kind it is. Assigned, received and suggested are kept apart; a
 * suggestion read from the file name is only ever a value after a person confirms it. */
export function ProductionNumbersPanel({ caseId, fileId }: { caseId: string; fileId: string }) {
  const overview = useProductionNumbers(caseId)
  const act = useProductionActions(caseId)
  const [first, setFirst] = useState("")
  const [last, setLast] = useState("")
  const [setName, setSetName] = useState("")
  const [prefix, setPrefix] = useState("")
  const [error, setError] = useState<string | null>(null)
  const numbers = overview.data?.files[fileId]
  const sets = overview.data?.sets ?? []
  const run = async (go: () => Promise<unknown>) => {
    setError(null)
    try {
      await go()
    } catch (e) {
      setError(e instanceof Error ? e.message : "Not saved")
    }
  }
  const line = (n: NumberItem, extra?: React.ReactNode) => (
    <li key={n.id ?? n.text} className="flex flex-wrap items-baseline gap-x-2 gap-y-1 text-sm" data-testid="production-number">
      <span className="font-mono">{n.text}</span>
      <span className="text-xs text-muted-foreground">
        {n.label ?? n.kind}
        {n.level === "file" && n.page_count == null ? " · file level only (no page count)" : ""}
        {n.withdrawn ? " · withdrawn" : ""}
      </span>
      {extra}
    </li>
  )
  return (
    <div className="space-y-2" data-testid="production-numbers">
      <ul className="space-y-1">
        {numbers?.assigned.map((n) => line(n, !n.withdrawn && n.id && (
          <button className="text-xs underline" onClick={() => run(() => act.withdraw.mutateAsync({ id: n.id!, reason: "Withdrawn from the file view" }))}>Withdraw</button>
        )))}
        {numbers?.received.filter((n) => !n.withdrawn).map((n) => line(n, n.id && (
          <button className="text-xs underline" onClick={() => run(() => act.withdrawReceived.mutateAsync(n.id!))}>Withdraw</button>
        )))}
        {numbers?.suggested.map((n) => line({ ...n, label: "Suggested from the file name · not confirmed" }, (
          <>
            <button className="text-xs underline" onClick={() => run(() => act.decide.mutateAsync({ fileId, first: n.first_text ?? "", last: n.last_text ?? "", confirm: true }))}>Confirm</button>
            <button className="text-xs underline" onClick={() => run(() => act.decide.mutateAsync({ fileId, first: n.first_text ?? "", last: n.last_text ?? "", confirm: false }))}>Reject</button>
          </>
        )))}
      </ul>
      {numbers && !numbers.assigned.length && !numbers.received.length && !numbers.suggested.length && (
        <p className="text-xs text-muted-foreground">No production number on this file.</p>
      )}
      {numbers?.conflicts.map((c) => (
        <p key={c.words} className="text-xs text-amber-700 dark:text-amber-400" data-testid="production-conflict">Conflict: {c.words}</p>
      ))}
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <input aria-label="Received first number" className="w-28 rounded border px-1 py-0.5" placeholder="First received" value={first} onChange={(e) => setFirst(e.target.value)} />
        <input aria-label="Received last number" className="w-28 rounded border px-1 py-0.5" placeholder="Last (optional)" value={last} onChange={(e) => setLast(e.target.value)} />
        <button className="underline disabled:opacity-50" disabled={!first.trim()}
          onClick={() => run(async () => { await act.enterReceived.mutateAsync({ fileId, first: first.trim(), last: last.trim() || undefined }); setFirst(""); setLast("") })}>
          Record received number
        </button>
      </div>
      <div className="flex flex-wrap items-center gap-2 text-xs">
        {sets.length === 0 ? (
          <>
            <input aria-label="Set name" className="w-24 rounded border px-1 py-0.5" placeholder="Set name" value={setName} onChange={(e) => setSetName(e.target.value)} />
            <input aria-label="Set prefix" className="w-24 rounded border px-1 py-0.5" placeholder="Prefix" value={prefix} onChange={(e) => setPrefix(e.target.value)} />
            <button className="underline disabled:opacity-50" disabled={!setName.trim() || !prefix.trim()}
              onClick={() => run(() => act.createSet.mutateAsync({ name: setName.trim(), prefix: prefix.trim(), start: 1, padding: 6 }))}>
              Create numbered set
            </button>
          </>
        ) : (
          <>
            <button className="underline" onClick={() => run(() => act.assign.mutateAsync({ setId: sets[0].id, fileId, level: "page" }))}>
              Assign next numbers from {sets[0].name} ({sets[0].next_text})
            </button>
            <button className="underline" onClick={() => run(() => act.assign.mutateAsync({ setId: sets[0].id, fileId, level: "file" }))}>
              Assign one number to the file
            </button>
          </>
        )}
      </div>
      {error && <p role="alert" className="text-xs text-destructive">{error}</p>}
    </div>
  )
}
