import { useQuery } from "@tanstack/react-query"
import { useState, type ReactNode } from "react"
import { Button } from "@/components/ui/button"
import { overlapAPI, type SharedPhrase } from "../api"
import { askCorroborate } from "../corroborate"

const SHOWN = 12

function Phrase({ p }: { p: SharedPhrase }) {
  return (
    <li>
      “{p.text}”: {p.copies} copies, {p.messages} {p.messages === 1 ? "message" : "messages"} counted once, on {p.phones.length} phones
      ({p.phone_labels.join(", ")}), on {p.dates.length} {p.dates.length === 1 ? "date" : "dates"}.
    </li>
  )
}

function Clipped<T>({ items, render, noun }: { items: T[]; render: (t: T, i: number) => ReactNode; noun: string }) {
  const [all, setAll] = useState(false)
  const shown = all ? items : items.slice(0, SHOWN)
  return (
    <>
      <ul className="list-disc space-y-0.5 pl-4">{shown.map(render)}</ul>
      {items.length > SHOWN && (
        <button type="button" className="text-[11px] underline" onClick={() => setAll(!all)}>
          {all ? "Show fewer" : `Show all ${items.length.toLocaleString("en-US")} ${noun}`}
        </button>
      )}
    </>
  )
}

/** The case's "Also elsewhere" and "Shown, but counted for nothing" lists (lx-overlapviews-b B, design screen 4). */
export function AlsoElsewherePanel({ caseId }: { caseId: string }) {
  const [open, setOpen] = useState(true)
  const q = useQuery({ queryKey: ["overlap-shared-words", caseId], queryFn: () => overlapAPI.sharedWords(caseId), staleTime: 120_000 })
  const r = q.data
  return (
    <aside aria-label="Also elsewhere" data-testid="also-elsewhere-panel" className="max-h-[40dvh] overflow-auto border-b bg-card px-3 py-2 text-xs">
      <div className="flex items-center gap-2">
        <h2 className="text-sm font-semibold">Also elsewhere</h2>
        {r && <span className="text-muted-foreground">{r.also.length} phrases, {r.deletions.length} deleted on one phone and kept on another</span>}
        <button type="button" className="ml-auto underline" onClick={() => setOpen(!open)}>{open ? "Hide the list" : "Show the list"}</button>
      </div>
      {q.isLoading && <p role="status">Reading every phone's messages…</p>}
      {q.isError && <p role="alert">The list could not be read. <Button size="sm" variant="link" onClick={() => void q.refetch()}>Try again</Button></p>}
      {r && open && (
        <div className="space-y-2 pt-1">
          <p className="text-muted-foreground">{r.rule}</p>
          <section aria-label="Words also on other phones">
            <h3 className="font-semibold">Words also on other phones</h3>
            {r.also.length === 0 ? <p>None in this case.</p> : <Clipped items={r.also} noun="phrases" render={(p) => <Phrase key={p.words} p={p} />} />}
            {r.also.length > 0 && (
              <Button size="sm" variant="outline" className="mt-1" onClick={() => askCorroborate({
                caseId, screen: "conversations", label: `${r.also.length} phrases on two or more phones`,
                members: r.also.flatMap((p) => p.records.map((id) => ({ type: "phone_record" as const, id, label: p.text }))),
              })}>Corroborate these</Button>
            )}
          </section>
          <section aria-label="Deleted on one phone, kept on another">
            <h3 className="font-semibold">Deleted on one phone, kept on another</h3>
            {r.deletions.length === 0 ? <p>None in this case.</p> : (
              <Clipped items={r.deletions} noun="messages" render={(d) => (
                <li key={d.records.join()}>“{d.text}”: deleted on {d.deleted_on.join(", ")}, still on {d.kept_on.join(", ")}.</li>
              )} />
            )}
          </section>
          {r.files_shared.length > 0 && (
            <section aria-label="Files on some phones">
              <h3 className="font-semibold">The same file on some phones</h3>
              <Clipped items={r.files_shared} noun="files" render={(f) => <li key={f.md5}>{f.name}: {f.phones.join(", ")}.</li>} />
            </section>
          )}
          <section aria-label="Shown, but counted for nothing" className="rounded bg-muted/50 p-2">
            <h3 className="font-semibold">Shown, but counted for nothing</h3>
            <p className="text-muted-foreground">Stock phrases ({r.stock.length}): on every phone or on many dates.</p>
            <Clipped items={r.stock} noun="stock phrases" render={(p) => (
              <li key={p.words}>“{p.text}”: {p.copies} copies on {p.phones.length} phones. {p.why}</li>
            )} />
            {r.files_common.length > 0 && (
              <p className="pt-1">Common files, the same bytes on all {r.phones_in_case} phones: {r.files_common.map((f) => f.name).join(", ")}.</p>
            )}
            {r.lookalikes.length > 0 && (
              <>
                <p className="pt-1">Pictures that look alike, for a person to check; never counted as the same photo:</p>
                <Clipped items={r.lookalikes} noun="pairs" render={(l) => (
                  <li key={`${l.a.file_uid}-${l.b.file_uid}`}>{l.a.name} on {l.a.phone} and {l.b.name} on {l.b.phone}: {l.bits_apart} of 64 bits apart ({l.level}).</li>
                )} />
              </>
            )}
            {r.lookalike_note && <p>{r.lookalike_note}</p>}
          </section>
        </div>
      )}
    </aside>
  )
}

export default AlsoElsewherePanel
