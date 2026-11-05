import { useQueries } from "@tanstack/react-query"
import { useCallback, useState, type UIEvent } from "react"
import { Button } from "@/components/ui/button"
import { shareFailure } from "../review-share"
import { fmt } from "../ui/count-sentence"
import { ExampleView } from "./ExampleView"
import { readingsAPI, type ConfirmKindResult, type Reading } from "./readings.api"

/**
 * "Looks right for all 12 rows of this kind on this phone" (07 J-8 step 6): every row is listed with its examples
 * first, and only the rows and example kinds on the screen are sent. Each row becomes a decision of its own under
 * this person, recorded as shown in a list rather than opened one by one; a row the server refuses is named with the
 * reason. The button waits until every row's examples are on the screen and the list has been read to its end.
 */
export function ConfirmKindPanel({ caseId, phone, rows, note, onClose, onDone }: { caseId: string; phone: string; rows: Reading[]; note: string; onClose: () => void; onDone: () => void }) {
  const [listed] = useState(rows)
  const examples = useQueries({
    queries: listed.map((r) => ({ queryKey: ["phone-reading-examples", caseId, r.id], queryFn: () => readingsAPI.examples(caseId, r.id) })),
  })
  const [busy, setBusy] = useState(false)
  const [atEnd, setAtEnd] = useState(false)
  const measure = useCallback((el: HTMLElement | null) => {
    if (el && el.scrollTop + el.clientHeight >= el.scrollHeight - 8) setAtEnd(true)
  }, [])
  const [error, setError] = useState<string | null>(null)
  const [done, setDone] = useState<ConfirmKindResult | null>(null)
  const ready = examples.filter((e) => e.data).length
  const failed = examples.filter((e) => e.isError).length
  const confirm = async () => {
    setBusy(true)
    setError(null)
    try {
      const body = listed.map((r, i) => {
        return { id: r.id, viewed: examples[i].data!.kinds.map((k) => k.id) }
      })
      setDone(await readingsAPI.confirmKind(caseId, body, note.trim() || undefined))
      onDone()
    } catch (e) {
      setError(shareFailure(e, "The rows could not be confirmed."))
    } finally {
      setBusy(false)
    }
  }
  if (done)
    return (
      <div className="flex flex-col gap-2 rounded border p-2 text-sm">
        <p role="status">{done.words}</p>
        {done.refused.length > 0 && (
          <ul aria-label="Refused rows" className="list-disc pl-5">
            {done.refused.map((x) => <li key={x.id}>{x.sentence ?? listed.find((r) => r.id === x.id)?.sentence ?? "A row"} {x.reason}</li>)}
          </ul>
        )}
        <div><Button size="sm" variant="outline" onClick={onClose}>Close</Button></div>
      </div>
    )
  return (
    <section aria-label="Every row of this kind" className="flex flex-col gap-2 rounded border p-2 text-sm">
      <p className="font-medium">{fmt(listed.length)} rows of this kind on {phone}. Each one is listed with its examples.</p>
      <ol ref={ready === listed.length ? measure : undefined} onScroll={(e: UIEvent<HTMLOListElement>) => measure(e.currentTarget)} className="flex max-h-[60vh] flex-col gap-3 overflow-auto">
        {listed.map((r, i) => (
          <li key={r.id} data-testid="kind-row" className="rounded border bg-card p-2">
            <p>{r.sentence}</p>
            {examples[i].isError && <p role="alert">The examples for this row could not be loaded.</p>}
            {examples[i].data?.kinds.map((k) => <ExampleView key={k.id} k={k} />)}
            {!examples[i].data && !examples[i].isError && <p role="status">Drawing examples from all {fmt(r.records)} records.</p>}
          </li>
        ))}
      </ol>
      {error && <p role="alert">{error}</p>}
      {failed > 0 && <p role="status">{fmt(failed)} of these rows could not show their examples, so they cannot be confirmed here. Open them one at a time.</p>}
      <div className="flex gap-2">
        <Button size="sm" disabled={busy || ready < listed.length || !atEnd} onClick={() => void confirm()}>Looks right for all {fmt(listed.length)} rows</Button>
        <Button size="sm" variant="outline" disabled={busy} onClick={onClose}>Cancel</Button>
        {ready < listed.length && !failed && <span role="status">Examples shown for {fmt(ready)} of {fmt(listed.length)} rows.</span>}
        {ready === listed.length && !atEnd && <span role="status">Read to the end of the list to confirm.</span>}
      </div>
    </section>
  )
}
