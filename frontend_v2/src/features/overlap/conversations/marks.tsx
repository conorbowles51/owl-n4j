import { useSwitch } from "@/lib/ui-switches"
import type { ThreadMarks } from "../api"

export function AlsoElsewhereToggle({ on, onChange }: { on: boolean; onChange: (on: boolean) => void }) {
  const allowed = useSwitch("corroborate-v2")
  if (!allowed) return null
  return (
    <label className="inline-flex items-center gap-1 text-xs" data-testid="also-elsewhere-toggle">
      <input type="checkbox" checked={on} onChange={(e) => onChange(e.target.checked)} />
      Mark what also appears elsewhere
    </label>
  )
}

/** The marks under one message: words also on other phones (or a stock phrase, counted for nothing) and what the
 * same number did on other phones meanwhile. */
export function RowMarks({ data, recordUid }: { data: ThreadMarks | undefined; recordUid: string }) {
  if (!data) return null
  const m = data.marks[recordUid]?.shared
  const mw = data.meanwhile[recordUid]
  if (!m && !mw) return null
  return (
    <div className="w-full space-y-0.5 text-xs" data-testid="also-elsewhere-mark">
      {m && !m.stock && (
        <p>
          <span className="rounded bg-amber-100 px-1 font-medium text-amber-900 dark:bg-amber-900/40 dark:text-amber-100">Also elsewhere</span>{" "}
          The same words in {m.messages} messages on {m.phones} phones on {m.dates} {m.dates === 1 ? "date" : "dates"}
          {m.other_phones.length ? `, also on ${m.other_phones.join(", ")}` : ""}. A message held on two phones is counted once.
        </p>
      )}
      {m && m.stock && <p className="text-muted-foreground">A stock phrase, counted for nothing: {m.why}</p>}
      {mw && (
        <div className="rounded border-l-2 border-sky-500 pl-2">
          <p className="font-medium">Meanwhile, from the same number</p>
          {mw.map((x) => (
            <p key={x.record_uid}>{x.time} on {x.phone}, {x.direction}: “{x.body}”</p>
          ))}
        </div>
      )}
    </div>
  )
}

/** The name each phone saved for the thread's numbers, and whose phone a number is. */
export function SavedNames({ data }: { data: ThreadMarks | undefined }) {
  if (!data || data.names.length === 0) return null
  return (
    <div className="w-full text-xs" data-testid="also-elsewhere-names">
      {data.names.map((n) => (
        <p key={n.number}>
          {n.number}: {n.names.length ? n.names.map((x) => `saved as “${x.name}” on ${x.phone}`).join("; ") : "saved on no phone"}
          {n.own_number_of ? `. This is the own number of ${n.own_number_of}` : ""}. <span className="text-muted-foreground">{n.note}</span>
        </p>
      ))}
    </div>
  )
}
