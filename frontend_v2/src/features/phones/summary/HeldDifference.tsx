import { useMutation, useQueryClient } from "@tanstack/react-query"
import { useState } from "react"
import { Button } from "@/components/ui/button"
import { acceptReconciliationDifference, failureText } from "../api"
import type { Profile } from "../schemas"
import { fmt } from "../ui/count-sentence"

type Held = Profile["completeness"]["held"]

/**
 * A held reconciliation difference (07 J-1, 03 section 7.3): "Held: the report lists ...; ... were read. See which."
 * See which lists every difference the check found (with the true total when more are stored than shown). The
 * choices are Accept the difference (typed reason, an accept_phone_reconciliation_difference decision, after which
 * the held reading resumes) and Keep held, which writes nothing and leaves the part out of every case view.
 */
export function HeldDifference({ caseId, extraction, words, held }: { caseId: string; extraction: string; words: string; held: Held }) {
  const qc = useQueryClient()
  const open = held.filter((h) => !h.accepted)
  const [showing, setShowing] = useState(false)
  const [mode, setMode] = useState<"choose" | "accept" | "kept">("choose")
  const [reason, setReason] = useState("")
  const [done, setDone] = useState<string | null>(null)
  const save = useMutation({
    mutationFn: () => acceptReconciliationDifference(caseId, extraction, reason.trim()),
    onSuccess: (out) => {
      setDone(`${fmt(out.differences)} ${out.differences === 1 ? "difference" : "differences"} accepted. ${out.restart.words}`)
      setReason("")
      void qc.invalidateQueries({ queryKey: ["phone-profile", caseId, extraction] })
    },
  })
  const total = open.reduce((n, h) => n + h.difference_count, 0)
  return (
    <div className="flex flex-col gap-1.5" aria-label="Held by the check">
      <p>
        {words}{" "}
        <button type="button" className="underline underline-offset-2" aria-expanded={showing} onClick={() => setShowing((v) => !v)}>
          {showing ? "Hide the list" : "See which"}
        </button>
      </p>
      {showing &&
        open.map((h) => (
          <div key={h.document_index} className="rounded border bg-background p-2 text-xs">
            <p className="font-medium">
              {h.document ?? `Document ${h.document_index + 1}`}: {fmt(h.difference_count)} {h.difference_count === 1 ? "difference" : "differences"}
              {h.shown < h.difference_count ? ` (the first ${fmt(h.shown)} are listed here)` : ""}
            </p>
            <table className="mt-1 w-full text-left">
              <thead>
                <tr>
                  <th className="pr-2 font-normal text-muted-foreground">Where in the report</th>
                  <th className="pr-2 font-normal text-muted-foreground">What was counted</th>
                  <th className="pr-2 text-right font-normal text-muted-foreground">The report lists</th>
                  <th className="text-right font-normal text-muted-foreground">Read</th>
                </tr>
              </thead>
              <tbody>
                {h.differences.map((d, i) => (
                  <tr key={i}>
                    <td className="pr-2">{d.where}</td>
                    <td className="pr-2">
                      {d.what}
                      {d.attribute ? ` (${d.attribute})` : ""}
                    </td>
                    {d.stated === null || d.read === null ? (
                      // a fingerprint of the values, not a count: the values differ, there is no number to show
                      <td className="text-right" colSpan={2}>Values differ</td>
                    ) : (
                      <>
                        <td className="pr-2 text-right">{fmt(d.stated)}</td>
                        <td className="text-right">{fmt(d.read)}</td>
                      </>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ))}
      {done ? (
        <p role="status">{done}</p>
      ) : mode === "kept" ? (
        <p role="status">
          Kept held. This part of the report stays out of every case view until a difference is accepted.{" "}
          <button type="button" className="underline underline-offset-2" onClick={() => setMode("choose")}>
            Change this
          </button>
        </p>
      ) : mode === "accept" ? (
        <form
          aria-label="Accept the difference"
          className="flex flex-col gap-1 text-xs"
          onSubmit={(e) => {
            e.preventDefault()
            if (reason.trim()) save.mutate()
          }}
        >
          <p>
            Accepting reads this part into the case views as it was read. The {fmt(total)} {total === 1 ? "difference stays" : "differences stay"} on record and the phone stays
            "Partly read".
          </p>
          <label className="flex flex-col gap-0.5">
            <span>Reason, in your own words</span>
            <textarea className="rounded border bg-background px-2 py-1" rows={2} value={reason} onChange={(e) => setReason(e.target.value)} />
          </label>
          <span className="flex items-center gap-2">
            <Button type="submit" size="sm" variant="outline" disabled={!reason.trim() || save.isPending}>
              Accept the difference
            </Button>
            <Button type="button" size="sm" variant="ghost" onClick={() => setMode("choose")} disabled={save.isPending}>
              Back
            </Button>
            {save.isPending && <span role="status">Saving</span>}
          </span>
          {save.isError && <p role="alert">{failureText(save.error, "The acceptance could not be saved.")}</p>}
        </form>
      ) : (
        <span className="flex gap-2">
          <Button type="button" size="sm" variant="outline" onClick={() => setMode("accept")}>
            Accept the difference
          </Button>
          <Button type="button" size="sm" variant="outline" onClick={() => setMode("kept")}>
            Keep held
          </Button>
        </span>
      )}
    </div>
  )
}
