import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useState } from "react"
import { useNavigate } from "react-router-dom"
import { Button } from "@/components/ui/button"
import { correctRecordValue, failureText, getRecordUses } from "../api"
import { liveCollectClient } from "../collect.api"
import { useCollectTargets } from "../collect-targets"
import type { RecordDetail } from "../schemas"
import { AddToMenu } from "../ui/AddToMenu"

/**
 * The record panel's actions and its Used in this case block (03 section 3.6 items 7 and 8): Show on Timeline (when
 * the record has a timeline entry), Show on Map (only when positioned), Add to… through the one collect menu, and
 * Correct this value (typed reason; the original is kept and shown beside the corrected value, and only the corrected
 * value is used). Used in this case is the reverse lookup of the record's collections, the same one the row badges
 * read, so the two always agree (CO-7).
 */
export function RecordActions({ detail, caseId }: { detail: RecordDetail; caseId: string }) {
  const navigate = useNavigate()
  const t = useCollectTargets(caseId)
  const qc = useQueryClient()
  const [correcting, setCorrecting] = useState(false)
  const uid = detail.record_uid
  const links = [{ target_type: "phone_record" as const, target_id: uid, label: detail.title ?? detail.model_type, source_anchor: { origin: "record_panel" } }]
  const correctable = detail.correctable ?? []
  return (
    <>
      <div className="flex flex-wrap gap-2" aria-label="More actions">
        {detail.on_timeline && (
          <Button size="sm" variant="outline" onClick={() => navigate(`/cases/${encodeURIComponent(caseId)}/timeline?phone_record=${encodeURIComponent(uid)}`)}>
            Show on Timeline
          </Button>
        )}
        {detail.position ? (
          <Button size="sm" variant="outline" onClick={() => navigate(`/cases/${encodeURIComponent(caseId)}/map?phone_point=${detail.position!.lon},${detail.position!.lat}`)}>
            Show on Map
          </Button>
        ) : detail.message_dated ? (
          // a message without its own position: the positions on the same phone within the hour of it (03 3.6 item 7)
          <Button size="sm" variant="outline" onClick={() => navigate(`/cases/${encodeURIComponent(caseId)}/map?phone_near=${encodeURIComponent(uid)}`)}>
            Show on Map
          </Button>
        ) : null}
        <AddToMenu
          caseId={caseId}
          links={links}
          noun="record"
          targets={t.targets}
          client={liveCollectClient}
          origin="Added from the record panel"
          keys={false}
          onAdded={() => void qc.invalidateQueries({ queryKey: ["record-uses", caseId, uid] })}
        />
        {correctable.length > 0 && (
          <Button size="sm" variant="outline" aria-expanded={correcting} onClick={() => setCorrecting((v) => !v)}>
            Correct this value
          </Button>
        )}
      </div>
      {t.note && <p className="text-xs text-muted-foreground">{t.note}</p>}
      {correcting && <CorrectValue caseId={caseId} detail={detail} onDone={() => setCorrecting(false)} />}
      <UsedInThisCase caseId={caseId} recordUid={uid} />
    </>
  )
}

function CorrectValue({ caseId, detail, onDone }: { caseId: string; detail: RecordDetail; onDone: () => void }) {
  const qc = useQueryClient()
  const values = detail.correctable ?? []
  const [pick, setPick] = useState(0)
  const v = values[pick]
  const [text, setText] = useState(v ? (v.corrected_text ?? v.machine_text ?? "") : "")
  const [reason, setReason] = useState("")
  const [done, setDone] = useState<string | null>(null)
  const save = useMutation({
    mutationFn: () => correctRecordValue(caseId, detail.record_uid, { field_path: v.field_path, value_index: v.value_index, corrected_text: text, reason: reason.trim(), expected_revision: v.revision }),
    onSuccess: () => {
      setDone(`Corrected. The phone's own value stays recorded and is shown beside the correction; the corrected value is the one searched, counted and exported once the phone is read again.`)
      setReason("")
      void qc.invalidateQueries({ queryKey: ["phone-record", caseId, detail.record_uid] })
    },
  })
  if (!v) return null
  const isTime = v.value_type === "TimeStamp"
  return (
    <form
      aria-label="Correct this value"
      className="flex flex-col gap-1.5 rounded border p-2 text-xs"
      onSubmit={(e) => {
        e.preventDefault()
        if (reason.trim() && text.trim()) save.mutate()
      }}
    >
      <label className="flex flex-col gap-0.5">
        <span className="font-medium">Value to correct</span>
        <select
          className="rounded border bg-background px-2 py-1"
          value={pick}
          onChange={(e) => {
            const i = Number(e.target.value)
            setPick(i)
            setText(values[i].corrected_text ?? values[i].machine_text ?? "")
            setDone(null)
          }}
        >
          {values.map((x, i) => (
            <option key={`${x.field_path}#${x.value_index}`} value={i}>
              {x.field_path}
              {x.value_index ? ` (value ${x.value_index + 1})` : ""}
              {x.corrected_text !== null ? " (corrected)" : ""}
            </option>
          ))}
        </select>
      </label>
      <p>
        As the phone recorded it: <span className="whitespace-pre-wrap">{v.machine_text ?? "(empty)"}</span>
        {v.corrected_text !== null && (
          <>
            {" "}
            Corrected to: <strong className="whitespace-pre-wrap">{v.corrected_text}</strong>
          </>
        )}
      </p>
      <label className="flex flex-col gap-0.5">
        <span>{isTime ? "Corrected time, with its offset from UTC (for example 2023-03-14T15:07:12-04:00)" : "Corrected value"}</span>
        {isTime ? (
          <input className="rounded border bg-background px-2 py-1" value={text} onChange={(e) => setText(e.target.value)} />
        ) : (
          <textarea className="rounded border bg-background px-2 py-1" rows={2} value={text} onChange={(e) => setText(e.target.value)} />
        )}
      </label>
      <label className="flex flex-col gap-0.5">
        <span>Reason, in your own words</span>
        <textarea className="rounded border bg-background px-2 py-1" rows={2} value={reason} onChange={(e) => setReason(e.target.value)} />
      </label>
      <span className="flex items-center gap-2">
        <Button type="submit" size="sm" variant="outline" disabled={!reason.trim() || !text.trim() || save.isPending}>
          Save correction
        </Button>
        <Button type="button" size="sm" variant="ghost" onClick={onDone}>
          Close
        </Button>
        {save.isPending && <span role="status">Saving</span>}
      </span>
      {save.isError && <p role="alert">{failureText(save.error, "The correction could not be saved.")}</p>}
      {done && !save.isError && <p role="status">{done}</p>}
    </form>
  )
}

function UsedInThisCase({ caseId, recordUid }: { caseId: string; recordUid: string }) {
  const q = useQuery({ queryKey: ["record-uses", caseId, recordUid], queryFn: () => getRecordUses(caseId, recordUid), staleTime: 10_000 })
  return (
    <section aria-label="Used in this case" className="text-xs">
      <h3 className="font-semibold">Used in this case</h3>
      {q.isLoading && <p className="text-muted-foreground">Looking up where this record is used</p>}
      {q.isError && <p role="alert">{failureText(q.error, "Where this record is used could not be looked up.")}</p>}
      {q.data && !q.data.summary && <p>Not yet in any finding, theory, note, dossier, interview or task.</p>}
      {q.data?.summary && (
        <>
          <p>{q.data.summary.replace(/^In /, "")}</p>
          <ul className="mt-0.5">
            {q.data.uses.map((u) => (
              <li key={`${u.kind}-${u.container_id}-${u.via}`}>
                {u.container_label ?? "(untitled)"} <span className="text-muted-foreground">({u.kind}{u.via === "selection" ? ", through a saved selection" : ""})</span>
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  )
}
