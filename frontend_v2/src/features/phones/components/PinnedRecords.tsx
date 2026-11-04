import { useQueries } from "@tanstack/react-query"
import { useState } from "react"
import { failureText, getRecord } from "../api"
import { fmt } from "../ui/count-sentence"
import { PhoneRecordPanel } from "./RecordPanel"

const PREVIEWED = 3

/**
 * The compact pinned preview of the record or records a Chat question or a Notebook note is about (03 section 3.6,
 * 07 section 4.3), so writing about a message never hides it. The first three are previewed, the rest counted;
 * Open the record opens the record panel beside the composer.
 */
export function PinnedRecords({ caseId, recordIds, total }: { caseId: string; recordIds: string[]; total?: number }) {
  const [open, setOpen] = useState<string | null>(null)
  const shown = recordIds.slice(0, PREVIEWED)
  const qs = useQueries({
    queries: shown.map((uid) => ({ queryKey: ["phone-record", caseId, uid, undefined], queryFn: () => getRecord(caseId, uid), staleTime: 60_000 })),
  })
  const all = Math.max(total ?? recordIds.length, recordIds.length)
  if (!shown.length) return null
  return (
    <div aria-label="Pinned records" className="flex flex-col gap-0.5 text-xs">
      <ul className="flex flex-col gap-0.5">
        {shown.map((uid, i) => {
          const q = qs[i]
          const d = q.data
          return (
            <li key={uid} className="flex items-baseline gap-2 rounded border bg-background px-1.5 py-0.5">
              <span className="min-w-0 flex-1 truncate">
                {q.isLoading && "Loading the record"}
                {q.isError && failureText(q.error, "This record could not be loaded.")}
                {d && `${d.extraction.label} · ${d.title ?? d.model_type} · ${d.times[0]?.full ?? "No time recorded"}`}
              </span>
              <button type="button" className="shrink-0 underline underline-offset-2" onClick={() => setOpen(uid)}>
                Open the record
              </button>
            </li>
          )
        })}
      </ul>
      {all > shown.length && <p className="text-muted-foreground">and {fmt(all - shown.length)} more</p>}
      <PhoneRecordPanel caseId={caseId} recordUid={open} onClose={() => setOpen(null)} />
    </div>
  )
}

/** The Notebook prefill from a phone selection (07 section 6, CO-6): "412 selected; all 412 will be linked", with the
 * records pinned. When the links carry fewer messages than were selected, the number linked is said instead. */
export function PhonePrefill({ caseId, selected, linked, recordIds }: { caseId: string; selected: number; linked: number; recordIds: string[] }) {
  return (
    <div className="mb-2 flex flex-col gap-1" data-testid="notebook-phone-prefill">
      <p role="status" className="text-xs">
        {fmt(selected)} selected; {linked === selected ? `all ${fmt(linked)} will be linked` : `${fmt(linked)} will be linked`}.
      </p>
      <PinnedRecords caseId={caseId} recordIds={recordIds} total={selected} />
    </div>
  )
}
