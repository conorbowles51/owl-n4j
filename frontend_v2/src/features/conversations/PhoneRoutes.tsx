import { useQuery } from "@tanstack/react-query"
import { useState } from "react"
import { Link, Navigate, useLocation, useParams } from "react-router-dom"
import { failureText, getPhones, getRecord } from "@/features/phones/api"
import { Button } from "@/components/ui/button"
import { ComparePhones } from "@/features/phones/components/ComparePhones"
import { phoneQueryTarget } from "./phone-query"

/**
 * The phone addresses Workspace, dossiers and Notebook links use (07 section 4.13; phone-links.ts). Each one lands
 * on the screen that shows the item: a thread or record opens Conversations at it, a person opens Conversations on
 * the people tab with that person chosen.
 */

export function PhonesIndexPage() {
  const { id: caseId = "" } = useParams()
  const location = useLocation()
  const target = phoneQueryTarget(caseId, location.search)
  const phones = useQuery({ queryKey: ["phones", caseId], queryFn: () => getPhones(caseId), enabled: !!caseId && !target })
  const [comparing, setComparing] = useState(false)
  if (target) return <Navigate to={target} replace />
  const q = new URLSearchParams(location.search)
  const unsupported = ["file", "selection", "view"].find((k) => q.get(k))
  return (
    <div className="flex flex-col gap-3 p-6">
      <h1 className="text-lg font-semibold">Phones</h1>
      {unsupported && (
        <p role="status" className="text-sm">
          This link names a phone {unsupported}. It opens on its own screen once that screen is released; the phones of the case are listed below.
        </p>
      )}
      {phones.isLoading && <p className="text-sm">Loading the phones</p>}
      {phones.isError && <p role="alert">{failureText(phones.error, "The phones could not be loaded.")}</p>}
      {phones.data && phones.data.phones.length === 0 && <p className="text-sm">This case has no phone yet.</p>}
      {(phones.data?.phones.length ?? 0) >= 2 && (
        <div>
          <Button size="sm" variant="outline" aria-expanded={comparing} onClick={() => setComparing((v) => !v)}>
            Compare phones
          </Button>
        </div>
      )}
      {comparing && phones.data && <ComparePhones caseId={caseId} phones={phones.data.phones} />}
      <ul className="flex flex-col gap-1">
        {(phones.data?.phones ?? []).map((p) => (
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
