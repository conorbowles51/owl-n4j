import { useMutation, useQueryClient } from "@tanstack/react-query"
import { useState } from "react"
import { Button } from "@/components/ui/button"
import { failureText, setPhoneLabel } from "../api"

/**
 * Name this phone (02 section 12.3): the name every screen uses for it. Saving writes a set_phone_label decision
 * with the reason; the name it replaces (from the report's file name, or "Phone <n>") stays in the decision record.
 */
export function NamePhone({ caseId, extraction, label }: { caseId: string; extraction: string; label: string }) {
  const qc = useQueryClient()
  const [name, setName] = useState("")
  const [reason, setReason] = useState("")
  const [done, setDone] = useState<string | null>(null)
  const save = useMutation({
    mutationFn: () => setPhoneLabel(caseId, extraction, name.trim(), reason.trim()),
    onSuccess: (r) => {
      setDone(`This phone is now called ${r.label}. The decision and your reason are in the case's decision record.`)
      setName("")
      setReason("")
      void qc.invalidateQueries({ queryKey: ["phone-profile", caseId, extraction] })
      void qc.invalidateQueries({ queryKey: ["phones", caseId] })
    },
  })
  return (
    <form
      aria-label="Name this phone"
      className="mt-2 flex flex-col gap-1.5 text-xs"
      onSubmit={(e) => {
        e.preventDefault()
        if (name.trim() && reason.trim()) save.mutate()
      }}
    >
      <label className="flex flex-col gap-0.5">
        <span className="font-medium">Name this phone (now {label})</span>
        <input className="rounded border bg-background px-2 py-1" maxLength={40} value={name} onChange={(e) => setName(e.target.value)} />
      </label>
      <label className="flex flex-col gap-0.5">
        <span>Reason, in your own words</span>
        <textarea className="rounded border bg-background px-2 py-1" rows={2} value={reason} onChange={(e) => setReason(e.target.value)} />
      </label>
      <span className="flex items-center gap-2">
        <Button type="submit" size="sm" variant="outline" disabled={!name.trim() || !reason.trim() || save.isPending}>
          Save name
        </Button>
        {save.isPending && <span role="status">Saving</span>}
      </span>
      {save.isError && <p role="alert">{failureText(save.error, "The name could not be saved.")}</p>}
      {done && !save.isError && <p role="status">{done}</p>}
    </form>
  )
}
