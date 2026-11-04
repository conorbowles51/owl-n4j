import { useQuery } from "@tanstack/react-query"
import { useState } from "react"
import { Link, Navigate, useLocation, useParams } from "react-router-dom"
import { failureText, getMediaDetail, getRecord, getSavedView } from "@/features/phones/api"
import { Button } from "@/components/ui/button"
import { ComparePhones } from "@/features/phones/components/ComparePhones"
import { phoneQueryTarget } from "./phone-query"
import { phonesQuery } from "@/features/phones/phones-query"

/**
 * The phone addresses Workspace, dossiers and Notebook links use (07 section 4.13; phone-links.ts). Each one lands
 * on the screen that shows the item: a thread or record opens Conversations at it, a person opens Conversations on
 * the people tab with that person chosen.
 */

export function PhonesIndexPage() {
  const { id: caseId = "" } = useParams()
  const location = useLocation()
  const target = phoneQueryTarget(caseId, location.search)
  const q = new URLSearchParams(location.search)
  const fileUid = q.get("file")
  // a saved phone_file link opens the file on its phone's Media screen
  const file = useQuery({ queryKey: ["phone-file-home", caseId, fileUid], queryFn: () => getMediaDetail(caseId, fileUid!), enabled: !!caseId && !!fileUid && !target, retry: false })
  // a saved phone_view link (07 section 6) re-opens the screen it was saved from, re-run live
  const viewId = q.get("view")
  const saved = useQuery({ queryKey: ["phone-view", caseId, viewId], queryFn: () => getSavedView(caseId, viewId!), enabled: !!caseId && !!viewId && !target, retry: false })
  const phones = useQuery({ ...phonesQuery(caseId), enabled: !!caseId && !target })
  const [comparing, setComparing] = useState(false)
  if (target) return <Navigate to={target} replace />
  if (saved.data && saved.data.location.startsWith(`/cases/${caseId}/`)) {
    const at = saved.data.location
    return <Navigate to={`${at}${at.includes("?") ? "&" : "?"}saved_view=${encodeURIComponent(saved.data.id)}`} replace />
  }
  if (file.data)
    return <Navigate to={`/cases/${encodeURIComponent(caseId)}/phones/${encodeURIComponent(file.data.extraction_id)}/records/media?file=${encodeURIComponent(fileUid!)}`} replace />
  // a report retired by Replace stays readable but is listed apart, so two reports of one phone never share a name
  const active = (phones.data?.phones ?? []).filter((p) => p.standing !== "superseded")
  const replaced = (phones.data?.phones ?? []).filter((p) => p.standing === "superseded")
  return (
    <div className="flex flex-col gap-3 p-6">
      <h1 className="text-lg font-semibold">Phones</h1>
      {viewId && saved.isLoading && <p role="status" className="text-sm">Opening the saved view</p>}
      {viewId && saved.isError && <p role="alert">{failureText(saved.error, "This saved view is not in this case.")}</p>}
      {fileUid && file.isLoading && <p role="status" className="text-sm">Opening the file</p>}
      {fileUid && file.isError && <p role="alert">{failureText(file.error, "This file is not in this case.")}</p>}
      {phones.isLoading && <p className="text-sm">Loading the phones</p>}
      {phones.isError && <p role="alert">{failureText(phones.error, "The phones could not be loaded.")}</p>}
      {phones.data && phones.data.phones.length === 0 && <p className="text-sm">This case has no phone yet.</p>}
      {active.length >= 2 && (
        <div>
          <Button size="sm" variant="outline" aria-expanded={comparing} onClick={() => setComparing((v) => !v)}>
            Compare phones
          </Button>
        </div>
      )}
      {comparing && phones.data && <ComparePhones caseId={caseId} phones={active} />}
      <ul className="flex flex-col gap-1">
        {active.map((p) => (
          <li key={p.extraction_id}>
            <Link className="underline underline-offset-2" to={`/cases/${caseId}/phones/${p.extraction_id}`}>
              {p.label}
            </Link>
            <span className="text-sm text-muted-foreground">
              {" "}
              {[p.device.manufacturer, p.device.model].filter(Boolean).join(" ") || "device not recorded"} · {p.counts.messages.toLocaleString("en-US")} messages,{" "}
              {p.counts.calls.toLocaleString("en-US")} calls, {p.counts.locations.toLocaleString("en-US")} locations
            </span>
          </li>
        ))}
      </ul>
      {replaced.length > 0 && (
        <section aria-label="Replaced reports" className="flex flex-col gap-1 text-sm">
          <h2 className="font-medium">Replaced reports</h2>
          <p className="text-muted-foreground">Retired by a newer report of the same phone. Their records stay readable and are not counted.</p>
          <ul className="flex flex-col gap-1">
            {replaced.map((p) => (
              <li key={p.extraction_id}>
                <Link className="underline underline-offset-2" to={`/cases/${caseId}/phones/${p.extraction_id}`}>
                  Replaced report: {p.label}
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  )
}

/** /phones/:extraction/records/:recordType?record= : messages open in Conversations at the record. */
export function PhoneRecordsRoute() {
  const { id: caseId = "", extraction = "" } = useParams()
  const location = useLocation()
  const q = new URLSearchParams(location.search)
  const record = q.get("record")
  const base = `/cases/${encodeURIComponent(caseId)}/phones/${encodeURIComponent(extraction)}/records/conversations`
  return <Navigate to={record ? `${base}?record=${encodeURIComponent(record)}` : base} replace />
}


/** /records/:recordUid : one phone record by id (rec:// citations, search hits). Finds the record's phone and opens
 * Conversations with the record beside it; says so plainly when the record is not in this case. */
export function RecordByIdRoute() {
  const { id: caseId = "", recordUid = "" } = useParams()
  const q = useQuery({ queryKey: ["phone-record", caseId, recordUid], queryFn: () => getRecord(caseId, recordUid), enabled: !!caseId && !!recordUid, retry: false })
  if (q.isLoading) return <p className="p-6 text-sm">Opening the record</p>
  if (q.isError || !q.data)
    return (
      <div role="alert" className="p-6 text-sm">
        {failureText(q.error, "This record is not in this case, or it could not be read.")}
      </div>
    )
  const base = `/cases/${encodeURIComponent(caseId)}/phones/${encodeURIComponent(q.data.extraction.id)}/records/conversations`
  return <Navigate to={`${base}?record=${encodeURIComponent(recordUid)}`} replace />
}
