import { LearnMore } from "@/components/ui/learn-more"
import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { fetchAPI } from "@/lib/api-client"
import { Button } from "@/components/ui/button"

export type DocumentDate = {
  id: string
  kind: "written" | "signed" | "period" | "received"
  date_from: string
  date_to: string
  source: "rule" | "model" | "person"
  words: string
  page: number | null
  confirmed: boolean
  confirmed_by: string | null
  label: string | null
  original: DocumentDate | null
}

const KIND: Record<DocumentDate["kind"], string> = {
  written: "Written",
  signed: "Signed",
  period: "Period",
  received: "Received",
}

const span = (d: DocumentDate) => (d.date_from === d.date_to ? d.date_from : `${d.date_from} to ${d.date_to}`)

/** Dates read from the document's text. A date Loupe read says so, with the words and page, until a person confirms it. */
export function DocumentDatesPanel({ caseId, fileId, canEdit }: { caseId: string; fileId: string; canEdit: boolean }) {
  const client = useQueryClient()
  const key = ["document-dates", caseId, fileId]
  const query = useQuery({
    queryKey: key,
    queryFn: () => fetchAPI<{ dates: DocumentDate[] }>(`/api/evidence/${fileId}/dates`),
  })
  const [editing, setEditing] = useState<string | null>(null)
  const [from, setFrom] = useState("")
  const [to, setTo] = useState("")
  const done = { onSuccess: () => { setEditing(null); return client.invalidateQueries({ queryKey: key }) } }
  const confirm = useMutation({
    mutationFn: (id: string) => fetchAPI(`/api/evidence/${fileId}/dates/${id}/confirm`, { method: "POST" }),
    ...done,
  })
  const correct = useMutation({
    mutationFn: (id: string) =>
      fetchAPI(`/api/evidence/${fileId}/dates/${id}/correct`, { method: "POST", body: { date_from: from, date_to: to || from } }),
    ...done,
  })
  const dates = query.data?.dates ?? []
  if (!dates.length) return null
  return (
    <div className="space-y-2 rounded-lg border p-3 text-xs" data-document-dates="" data-guide="document-dates">
      <p className="font-medium">Dates in the document <LearnMore term="Read by Loupe not confirmed" /></p>
      {dates.map((d) => {
        const target = d.original ?? d
        return (
          <div key={d.id} className="space-y-1 border-t pt-2 first:border-t-0 first:pt-0">
            <p>
              <span className="font-medium">{KIND[d.kind]}: {span(d)}</span>{" "}
              <span className="text-muted-foreground">
                {d.source === "person" ? `Corrected by ${d.confirmed_by ?? "a person"}` : d.label ?? `Confirmed by ${d.confirmed_by ?? "a person"}`}
              </span>
            </p>
            {d.original && (
              <p className="text-muted-foreground">
                Read by Loupe: {span(d.original)}. This reading stays on record; the corrected date is the one used.
              </p>
            )}
            {(d.original ?? d).words && (
              <p className="text-muted-foreground">
                “{(d.original ?? d).words}”{(d.original ?? d).page ? `, page ${(d.original ?? d).page}` : ""}
              </p>
            )}
            {canEdit && editing !== d.id && (
              <div className="flex gap-2">
                {!d.confirmed && (
                  <Button size="sm" variant="outline" disabled={confirm.isPending} onClick={() => confirm.mutate(d.id)}>
                    Confirm
                  </Button>
                )}
                <Button size="sm" variant="ghost" onClick={() => { setEditing(d.id); setFrom(d.date_from); setTo(d.date_to) }}>
                  Correct
                </Button>
              </div>
            )}
            {editing === d.id && (
              <div className="flex flex-wrap items-center gap-2">
                <input type="date" aria-label="From" value={from} onChange={(e) => setFrom(e.target.value)} className="rounded border px-1" />
                <input type="date" aria-label="To" value={to} onChange={(e) => setTo(e.target.value)} className="rounded border px-1" />
                <Button size="sm" disabled={!from || correct.isPending} onClick={() => correct.mutate(target.id)}>
                  Save
                </Button>
                <Button size="sm" variant="ghost" onClick={() => setEditing(null)}>Cancel</Button>
              </div>
            )}
            {(confirm.error || correct.error) && editing === d.id && (
              <p role="alert" className="text-destructive">The date could not be saved.</p>
            )}
          </div>
        )
      })}
    </div>
  )
}
