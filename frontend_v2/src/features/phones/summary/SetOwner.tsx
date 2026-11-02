import { useMutation, useQueryClient } from "@tanstack/react-query"
import { useEffect, useState } from "react"
import { Button } from "@/components/ui/button"
import { failureText, setOwner } from "../api"
import type { Profile } from "../schemas"

/**
 * Set the owner (03 section 7.3): choose one of the numbers this phone shows and say why. Saving writes a
 * set_phone_owner decision with the reason; the system's own candidates stay listed with how often each was seen.
 */
export function SetOwner({ caseId, extraction, owner }: { caseId: string; extraction: string; owner: Profile["owner"] }) {
  const qc = useQueryClient()
  const current = owner.keys[0] ?? ""
  const [key, setKey] = useState("")
  const [reason, setReason] = useState("")
  const [done, setDone] = useState<string | null>(null)
  useEffect(() => {
    // arriving from a "Set the owner" link elsewhere (…/phones/<id>#set-owner) lands on the control
    if (window.location.hash === "#set-owner") document.getElementById("set-owner-number")?.focus()
  }, [])
  const save = useMutation({
    mutationFn: async () => {
      await setOwner(caseId, extraction, key, reason.trim())
    },
    onSuccess: () => {
      const chosen = owner.candidates.find((c) => c.identity_key === key)
      setDone(`Owner set to ${chosen?.text ?? key}. The decision and your reason are in the case's decision record.`)
      setReason("")
      void qc.invalidateQueries({ queryKey: ["phone-profile", caseId, extraction] })
    },
  })
  if (owner.candidates.length === 0)
    return <p className="mt-2 text-xs">No number on this phone to choose from as its owner.</p>
  return (
    <form
      id="set-owner"
      aria-label="Set the owner"
      className="mt-2 flex flex-col gap-1.5 text-xs"
      onSubmit={(e) => {
        e.preventDefault()
        if (key && reason.trim()) save.mutate()
      }}
    >
      <label className="flex flex-col gap-0.5">
        <span className="font-medium">Set the owner</span>
        <select id="set-owner-number" className="rounded border bg-background px-2 py-1" value={key} onChange={(e) => setKey(e.target.value)}>
          <option value="">Choose a number this phone shows</option>
          {owner.candidates.map((c) => (
            <option key={c.identity_key} value={c.identity_key}>
              {c.text}
              {c.identity_key === current ? " (current owner)" : ""}: seen {c.occurrences.toLocaleString("en-US")} {c.occurrences === 1 ? "time" : "times"}
            </option>
          ))}
        </select>
      </label>
      <label className="flex flex-col gap-0.5">
        <span>Reason, in your own words</span>
        <textarea className="rounded border bg-background px-2 py-1" rows={2} value={reason} onChange={(e) => setReason(e.target.value)} />
      </label>
      <span className="flex items-center gap-2">
        <Button type="submit" size="sm" variant="outline" disabled={!key || !reason.trim() || save.isPending}>
          Save owner
        </Button>
        {save.isPending && <span role="status">Saving</span>}
      </span>
      {save.isError && <p role="alert">{failureText(save.error, "The owner could not be saved.")}</p>}
      {done && !save.isError && <p role="status">{done}</p>}
    </form>
  )
}
