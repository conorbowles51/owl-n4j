import { useMutation, useQueries, useQuery, useQueryClient } from "@tanstack/react-query"
import { useEffect, useRef, useState } from "react"
import { Link } from "react-router-dom"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { getExternalProcessing, getPhones, getSettings, putCaseRegion, putSettings, putTowerReference, setExternalProcessing } from "@/features/phones/api"
import type { PhoneSettings } from "@/features/phones/api"
import { setupError, ZONES } from "@/features/phones/summary/setup-words"

/**
 * Case settings, Phones (07 section 5): the case time zone, default country and tower reference, and each phone's
 * outside-processing decision with its plain consequence, beside the case's blur default (MediaBlurSetting). The
 * outside-processing decision covers other outbound services only (plan standing decision 8); the system owner makes
 * it, phone by phone.
 */
export function CasePhonesSection({ caseId, isSuperAdmin, isAdmin = isSuperAdmin }: { caseId: string; isSuperAdmin: boolean; isAdmin?: boolean }) {
  const phones = useQuery({ queryKey: ["phones", caseId], queryFn: () => getPhones(caseId) })
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (window.location.hash === "#phones" && phones.data?.phones.length) ref.current?.scrollIntoView({ block: "start" })
  }, [phones.data])
  const list = phones.data?.phones ?? []
  if (list.length === 0) return null
  return (
    <div id="phones" ref={ref}>
      <Card className="mt-6 gap-4 p-5">
        <CardHeader>
          <CardTitle className="text-base">Phones</CardTitle>
          <CardDescription>Settings for the phones in this case. Each phone's own choices are on its Phone summary.</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4 text-sm">
          <CaseSettings caseId={caseId} isAdmin={isAdmin} />
          <section aria-label="Outside services" className="flex flex-col gap-1">
            <h3 className="text-sm font-medium">Outside services</h3>
            <p className="text-xs text-muted-foreground">
              Allowing a phone sends its material to outside services for embeddings, transcription, translation, image search and geocoding. With no decision, nothing from that phone goes to them.
              {!isSuperAdmin && " Only the system owner can decide this."}
            </p>
            <ExternalList caseId={caseId} phones={list.map((p) => ({ id: p.extraction_id, label: p.label }))} isSuperAdmin={isSuperAdmin} />
          </section>
        </CardContent>
      </Card>
    </div>
  )
}

const selectClass = "rounded border bg-background px-2 py-1 text-xs"

function CaseSettings({ caseId, isAdmin }: { caseId: string; isAdmin: boolean }) {
  const qc = useQueryClient()
  const key = ["phone-settings", caseId]
  const q = useQuery({ queryKey: key, queryFn: () => getSettings(caseId) })
  const refresh = () => void qc.invalidateQueries({ queryKey: key })
  if (q.isLoading) return <p className="text-xs text-muted-foreground">Reading the settings…</p>
  if (q.isError || !q.data) return <p role="alert" className="text-xs text-destructive">The settings could not be read. Nothing has changed.</p>
  return (
    <>
      <ZoneSetting caseId={caseId} data={q.data} onSaved={refresh} />
      <RegionSetting caseId={caseId} data={q.data} onSaved={refresh} />
      <TowerSetting caseId={caseId} data={q.data} isAdmin={isAdmin} onSaved={refresh} />
    </>
  )
}

function ZoneSetting({ caseId, data, onSaved }: { caseId: string; data: PhoneSettings; onSaved: () => void }) {
  const [zone, setZone] = useState(data.effective.name)
  const save = useMutation({ mutationFn: () => putSettings(caseId, zone), onSuccess: onSaved })
  return (
    <section aria-label="Time zone" className="flex flex-col gap-1">
      <h3 className="text-sm font-medium">Time zone</h3>
      <p className="text-xs text-muted-foreground">Times on the phone screens are shown in {data.effective.name}.{data.effective.note ? ` ${data.effective.note}` : ""}{data.updated_by ? ` Set by ${data.updated_by}.` : ""}</p>
      <span className="flex flex-wrap items-center gap-2">
        <select aria-label="Case time zone" className={selectClass} value={zone} onChange={(e) => setZone(e.target.value)}>
          {[...new Set([data.effective.name, ...ZONES()])].map((z) => <option key={z} value={z}>{z}</option>)}
        </select>
        <Button size="sm" variant="outline" disabled={zone === data.effective.name || save.isPending} onClick={() => save.mutate()}>Save time zone</Button>
      </span>
      {save.isError && <p role="alert" className="text-xs">{setupError(save.error, "This could not be saved. Nothing changed.")}</p>}
    </section>
  )
}

function RegionSetting({ caseId, data, onSaved }: { caseId: string; data: PhoneSettings; onSaved: () => void }) {
  const region = data.default_region
  const current = region?.region ?? ""
  const [value, setValue] = useState(current)
  const [reason, setReason] = useState("")
  const save = useMutation({
    mutationFn: () => putCaseRegion(caseId, value || null, reason.trim()),
    onSuccess: () => { setReason(""); onSaved() },
  })
  if (!region) return null
  return (
    <section aria-label="Default country" className="flex flex-col gap-1">
      <h3 className="text-sm font-medium">Default country</h3>
      <p className="text-xs text-muted-foreground">{region.words} Changing it reads those phones again.</p>
      <select aria-label="Case default country" className={`${selectClass} self-start`} value={value} onChange={(e) => setValue(e.target.value)}>
        <option value="">No case default</option>
        {region.regions.map((r) => <option key={r.code} value={r.code}>{r.name}</option>)}
      </select>
      {value !== current && (
        <form
          aria-label="Change the default country"
          className="flex flex-col gap-1 text-xs"
          onSubmit={(e) => {
            e.preventDefault()
            if (reason.trim()) save.mutate()
          }}
        >
          <label className="flex flex-col gap-0.5">
            <span>Reason, in your own words</span>
            <textarea className="rounded border bg-background px-2 py-1" rows={2} value={reason} onChange={(e) => setReason(e.target.value)} />
          </label>
          <Button type="submit" size="sm" variant="outline" className="self-start" disabled={!reason.trim() || save.isPending}>Save and read again</Button>
        </form>
      )}
      {save.isError && <p role="alert" className="text-xs">{setupError(save.error, "This could not be saved. Nothing changed.")}</p>}
    </section>
  )
}

function TowerSetting({ caseId, data, isAdmin, onSaved }: { caseId: string; data: PhoneSettings; isAdmin: boolean; onSaved: () => void }) {
  const cell = data.cell_reference
  const current = cell?.in_use?.id ?? ""
  const [value, setValue] = useState(current)
  const [reason, setReason] = useState("")
  const save = useMutation({
    mutationFn: () => putTowerReference(caseId, value || null, reason.trim()),
    onSuccess: () => { setReason(""); onSaved() },
  })
  if (!cell) return null
  const inUse = cell.in_use
  return (
    <section aria-label="Tower reference" className="flex flex-col gap-1">
      <h3 className="text-sm font-medium">Tower reference</h3>
      <p className="text-xs text-muted-foreground">
        {inUse
          ? `In use: ${inUse.name}${inUse.retrieved_on ? `, retrieved ${inUse.retrieved_on}` : ""}, chosen by ${inUse.chosen_by}.`
          : cell.datasets.length ? "None in use, so cell towers are not placed on the map." : "None on this server, so cell towers are not placed on the map."}
        {!isAdmin && " Only an administrator can change this."}
      </p>
      {isAdmin && cell.datasets.length > 0 && (
        <>
          <select aria-label="Tower reference for this case" className={`${selectClass} self-start`} value={value} onChange={(e) => setValue(e.target.value)}>
            <option value="">None</option>
            {cell.datasets.map((d) => <option key={d.id} value={d.id}>{d.name}{d.retrieved_on ? `, ${d.retrieved_on}` : ""}</option>)}
          </select>
          {value !== current && (
            <form
              aria-label="Change the tower reference"
              className="flex flex-col gap-1 text-xs"
              onSubmit={(e) => {
                e.preventDefault()
                if (reason.trim()) save.mutate()
              }}
            >
              <label className="flex flex-col gap-0.5">
                <span>Reason, in your own words</span>
                <textarea className="rounded border bg-background px-2 py-1" rows={2} value={reason} onChange={(e) => setReason(e.target.value)} />
              </label>
              <Button type="submit" size="sm" variant="outline" className="self-start" disabled={!reason.trim() || save.isPending}>Save and read again</Button>
            </form>
          )}
          {save.isError && <p role="alert" className="text-xs">{setupError(save.error, "This could not be saved. Nothing changed.")}</p>}
        </>
      )}
    </section>
  )
}

function ExternalList({ caseId, phones, isSuperAdmin }: { caseId: string; phones: { id: string; label: string }[]; isSuperAdmin: boolean }) {
  const states = useQueries({
    queries: phones.map((p) => ({ queryKey: ["phone-external", caseId, p.id], queryFn: () => getExternalProcessing(caseId, p.id) })),
  })
  return (
    <ul className="flex flex-col gap-1.5">
      {phones.map((p, i) => (
        <ExternalRow key={p.id} caseId={caseId} phone={p} state={states[i]?.data} failed={!!states[i]?.isError} isSuperAdmin={isSuperAdmin} />
      ))}
    </ul>
  )
}

function ExternalRow({ caseId, phone, state, failed, isSuperAdmin }: {
  caseId: string
  phone: { id: string; label: string }
  state?: Awaited<ReturnType<typeof getExternalProcessing>>
  failed: boolean
  isSuperAdmin: boolean
}) {
  const qc = useQueryClient()
  const [open, setOpen] = useState(false)
  const [reason, setReason] = useState("")
  const allowed = !!state?.external_processing
  const save = useMutation({
    mutationFn: () => setExternalProcessing(caseId, phone.id, !allowed, reason.trim()),
    onSuccess: () => {
      setOpen(false)
      setReason("")
      void qc.invalidateQueries({ queryKey: ["phone-external", caseId, phone.id] })
    },
  })
  return (
    <li className="flex flex-col gap-1 text-xs">
      <span>
        <Link className="font-medium underline underline-offset-2" to={`/cases/${encodeURIComponent(caseId)}/phones/${encodeURIComponent(phone.id)}`}>
          {phone.label}
        </Link>
        : {failed ? "This decision could not be read." : !state ? "Reading" : allowed ? `Allowed${state.decided_by ? ` by ${state.decided_by}` : ""}${state.reason ? `: ${state.reason}` : ""}.` : "Not allowed."}{" "}
        {isSuperAdmin && state && (
          <button type="button" className="underline underline-offset-2" aria-expanded={open} onClick={() => setOpen((v) => !v)}>
            {open ? "Close" : allowed ? "Withdraw" : "Allow"}
          </button>
        )}
      </span>
      {open && (
        <form
          aria-label={`Outside services for ${phone.label}`}
          className="flex flex-col gap-1"
          onSubmit={(e) => {
            e.preventDefault()
            if (reason.trim()) save.mutate()
          }}
        >
          <label className="flex flex-col gap-0.5">
            <span>Reason, in your own words</span>
            <textarea className="rounded border bg-background px-2 py-1" rows={2} value={reason} onChange={(e) => setReason(e.target.value)} />
          </label>
          <Button type="submit" size="sm" variant="outline" className="self-start" disabled={!reason.trim() || save.isPending}>
            {allowed ? "Withdraw for this phone" : "Allow for this phone"}
          </Button>
          {save.isError && <p role="alert">{setupError(save.error, "This could not be saved. Nothing changed.")}</p>}
        </form>
      )}
    </li>
  )
}
