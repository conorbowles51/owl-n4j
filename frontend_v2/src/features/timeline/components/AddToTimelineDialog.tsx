import { useEffect, useState } from "react"
import { useLocation, useNavigate } from "react-router-dom"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { fetchAPI } from "@/lib/api-client"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog"
import { useCaseLayerStore } from "@/features/significant/stores/case-layer.store"
import type { TimelineEvent } from "../api"
import { hasAmount } from "../api"

type Preview = {
  case_id: string
  revision: string
  ready: number
  already_added: number
  undated: number
  rows: {
    source_id: string
    name: string
    status: "ready" | "already_added" | "undated"
    event: TimelineEvent | null
  }[]
}
type Receipt = {
  case_id: string
  added: number
  already_added: number
  undated: number
  event_keys: string[]
}
const explainError = (error: Error) =>
  error.message.length > 400 || /^[{[]/.test(error.message)
    ? "The selection could not be added. Refresh the preview and try again."
    : error.message

export function AddToTimelineDialog({
  caseId,
  ids,
  sourceKind = "transaction",
  title,
  onClose,
}: {
  caseId: string
  ids: string[]
  sourceKind?: "transaction" | "workspace_entry" | "money_trail" | "evidence_file"
  title?: string
  onClose: () => void
}) {
  const navigate = useNavigate()
  const location = useLocation()
  const client = useQueryClient()
  const [eventDate, setEventDate] = useState("")
  const [eventTime, setEventTime] = useState("")
  const [place, setPlace] = useState("")
  const isFile = sourceKind === "evidence_file"
  const [preview, setPreview] = useState<Preview | null>(null)
  const [receipt, setReceipt] = useState<Receipt | null>(null)
  const body = {
    source_kind: sourceKind,
    source_ids: ids,
    ...(eventDate ? { event_date: eventDate } : {}),
    ...(isFile && eventTime ? { event_time: eventTime } : {}),
    ...(isFile && place.trim() ? { place: place.trim() } : {}),
  }
  const url = `/api/timeline/entries?${new URLSearchParams({ case_id: caseId })}`
  const review = useMutation({
    mutationFn: async () => {
      if (ids.length > 5000)
        throw Error(
          "Select up to 5,000 transactions at a time to add to Timeline."
        )
      const result = await fetchAPI<Preview>(
        url.replace("entries?", "entries/preview?"),
        { method: "POST", body }
      )
      if (result.case_id !== caseId || result.rows.length !== new Set(ids).size)
        throw Error(
          "The preview does not match this selection. Refresh and try again."
        )
      setPreview(result)
    },
  })
  // Files open with their preview already loaded, so each photo's own date shows before anything is typed.
  const startReview = review.mutate
  useEffect(() => {
    if (isFile) startReview()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
  const save = useMutation({
    mutationFn: async () => {
      const result = await fetchAPI<Receipt>(url, {
        method: "POST",
        body: { ...body, expected_revision: preview?.revision },
      })
      if (result.case_id !== caseId)
        throw Error(
          "The response did not match this case. Refresh before continuing."
        )
      setReceipt(result)
      await client.invalidateQueries({ queryKey: ["timeline", caseId] })
    },
  })
  const openTimeline = (keys: string[]) => {
    useCaseLayerStore.getState().setLayer(caseId, "all")
    onClose()
    navigate(`/cases/${caseId}/timeline?event=${encodeURIComponent(keys[0])}`, {
      state: {
        timelineAddedKeys: keys,
        financialReturnTo: location.pathname + location.search,
      },
    })
  }
  const pending = review.isPending || save.isPending
  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open && !pending) onClose()
      }}
    >
      <DialogContent className="flex max-h-[85vh] max-w-2xl flex-col overflow-hidden">
        <DialogTitle>Add to Timeline</DialogTitle>
        <DialogDescription>
          {title ||
            `${ids.length} selected ${isFile ? "file" : "transaction"}${ids.length === 1 ? "" : "s"}`}{" "}
          · Add dated events to this case’s Timeline with links back to their
          sources.
        </DialogDescription>
        <div className="min-h-0 flex-1 overflow-y-auto space-y-3 pr-2">
          {receipt ? (
            <div role="status" className="space-y-2">
              <p className="font-semibold">
                {receipt.added} added to Timeline.
              </p>
              {receipt.already_added > 0 && (
                <p>
                  {receipt.already_added} already on Timeline; no duplicates
                  added.
                </p>
              )}
              {receipt.undated > 0 && (
                <p>
                  {isFile
                    ? `${receipt.undated} had no date in their data and were not added. Choose a date and add them again.`
                    : `${receipt.undated} undated payments were left in Transactions. Edit their dates and add them when ready.`}
                </p>
              )}
              <p>
                Open Timeline to see these entries alongside the other events in
                this case. Select an entry to inspect its source.
              </p>
            </div>
          ) : (
            <>
              {isFile ? (
                <div className="grid gap-2 text-sm">
                  <p>
                    Each photo goes on the Timeline at the date in its own data. That date is not checked by a
                    person. Change the date, time or place below if it is wrong; the photo’s own value stays
                    visible on the entry.
                  </p>
                  <div className="flex flex-wrap gap-3">
                    <label className="grid gap-1">
                      Date (all selected)
                      <input type="date" className="rounded border p-2 bg-background" value={eventDate}
                        disabled={pending}
                        onChange={(e) => { setEventDate(e.target.value); setPreview(null); save.reset() }} />
                    </label>
                    <label className="grid gap-1">
                      Time
                      <input type="time" className="rounded border p-2 bg-background" value={eventTime}
                        disabled={pending}
                        onChange={(e) => { setEventTime(e.target.value); setPreview(null); save.reset() }} />
                    </label>
                    <label className="grid min-w-48 flex-1 gap-1">
                      Place (optional)
                      <input type="text" maxLength={200} className="rounded border p-2 bg-background" value={place}
                        disabled={pending}
                        onChange={(e) => { setPlace(e.target.value); setPreview(null); save.reset() }} />
                    </label>
                  </div>
                  <span className="text-muted-foreground">Leave all three blank to use each photo’s own data. A description is not needed.</span>
                </div>
              ) : sourceKind === "money_trail" ? (
                <p>
                  One transfer event retains both statement entries as
                  supporting evidence. Existing individual entries are combined
                  in the main Timeline; their saved copies remain available in
                  earlier views. The subsequent supplier payment is a separate
                  event.
                </p>
              ) : sourceKind === "workspace_entry" ? (
                <label className="grid gap-1 text-sm">
                  Event date
                  <input
                    type="date"
                    className="rounded border p-2 bg-background"
                    value={eventDate}
                    disabled={pending}
                    onChange={(e) => {
                      setEventDate(e.target.value)
                      setPreview(null)
                      save.reset()
                    }}
                  />
                  <span className="text-muted-foreground">
                    Choose when the described event happened. This does not
                    change the finding or observation’s creation date.
                  </span>
                </label>
              ) : (
                <p className="text-sm">
                  Uses each payment’s transaction date, or its recorded posted,
                  value or effective date when needed. A statement period alone
                  cannot place a payment on Timeline.
                </p>
              )}
              {!preview && (
                <Button
                  disabled={
                    pending || (sourceKind === "workspace_entry" && !eventDate)
                  }
                  onClick={() => review.mutate()}
                >
                  {review.isPending
                    ? "Loading preview…"
                    : "Review Timeline entries"}
                </Button>
              )}
              {preview && (
                <>
                  <p className="font-semibold">
                    {preview.ready} ready · {preview.already_added} already
                    added
                    {sourceKind === "transaction" && (
                      <> · {preview.undated} without a payment date</>
                    )}
                    {isFile && <> · {preview.undated} without a date</>}
                  </p>
                  <ul className="divide-y rounded border">
                    {preview.rows.map((row) => (
                      <li key={row.source_id} className="p-3 space-y-1 text-sm">
                        <p className="font-medium break-words">{row.name}</p>
                        <p>
                          {row.event
                            ? `${row.event.date} · ${row.event.type} · ${row.event.source?.date_basis ?? "Recorded date"}`
                            : isFile
                              ? "No date taken in the photo’s data. Choose a date above to add it."
                              : "No payment date — will not be added"}
                        </p>
                        {row.event && hasAmount(row.event.amount) && <p>{row.event.amount}</p>}
                        {row.event?.source?.label && (
                          <p className="text-muted-foreground break-words">
                            {row.event.source.label}
                          </p>
                        )}
                        {row.status === "already_added" && (
                          <p>
                            Already on Timeline; keeps its existing event date.
                          </p>
                        )}
                      </li>
                    ))}
                  </ul>
                </>
              )}
            </>
          )}
          {(review.error || save.error) && (
            <p role="alert" className="text-destructive">
              {explainError((review.error || save.error) as Error)}
            </p>
          )}
        </div>
        <footer className="flex shrink-0 flex-wrap gap-2 border-t pt-3">
          {receipt?.event_keys.length ? (
            <Button onClick={() => openTimeline(receipt.event_keys)}>
              Open Timeline
            </Button>
          ) : null}
          {!receipt && preview && (
            <>
              {preview.ready > 0 && (
                <Button disabled={pending} onClick={() => save.mutate()}>
                  {save.isPending
                    ? "Adding…"
                    : `Add ${preview.ready} to Timeline`}
                </Button>
              )}
              {!preview.ready && preview.already_added > 0 && (
                <Button
                  onClick={() =>
                    openTimeline(
                      preview.rows.flatMap((row) =>
                        row.event ? [row.event.key] : []
                      )
                    )
                  }
                >
                  Open Timeline
                </Button>
              )}
              <Button
                variant="outline"
                disabled={pending}
                onClick={() => {
                  save.reset()
                  review.mutate()
                }}
              >
                Refresh preview
              </Button>
            </>
          )}
          <Button variant="outline" disabled={pending} onClick={onClose}>
            {receipt ? "Done" : "Cancel"}
          </Button>
        </footer>
      </DialogContent>
    </Dialog>
  )
}
