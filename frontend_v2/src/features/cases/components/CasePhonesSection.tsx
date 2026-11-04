import { useMutation, useQueries, useQuery, useQueryClient } from "@tanstack/react-query"
import { useEffect, useRef, useState } from "react"
import { Link } from "react-router-dom"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { getExternalProcessing, getPhones, setExternalProcessing } from "@/features/phones/api"
import { setupError } from "@/features/phones/summary/setup-words"

/**
 * Case settings, Phones (07 section 5): each phone's outside-processing decision with its plain consequence, beside
 * the case's blur default (MediaBlurSetting). The decision covers other outbound services only (plan standing decision
 * 8); the system owner makes it, phone by phone.
 */
export function CasePhonesSection({ caseId, isSuperAdmin }: { caseId: string; isSuperAdmin: boolean }) {
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
