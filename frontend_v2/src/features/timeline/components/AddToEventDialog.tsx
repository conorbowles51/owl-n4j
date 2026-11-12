import { useMemo, useState } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { fetchAPI } from "@/lib/api-client"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog"
import { useTimelineData } from "../hooks/use-timeline-data"

const SHOWN = 50

/** Attach files (photos first) to an event already on the case Timeline. No description is asked for. */
export function AddToEventDialog({
  caseId,
  files,
  onClose,
  onDone,
}: {
  caseId: string
  files: Array<{ id: string; name: string }>
  onClose: () => void
  onDone?: () => void
}) {
  const client = useQueryClient()
  const timeline = useTimelineData({ caseId })
  const [search, setSearch] = useState("")
  const [chosen, setChosen] = useState<string | null>(null)
  const [receipt, setReceipt] = useState<{ added: number; already_attached: number } | null>(null)
  const matches = useMemo(() => {
    const term = search.trim().toLowerCase()
    return timeline.events
      .filter((event) => !event.key.startsWith("photo:") || term)
      .filter((event) => !term || `${event.name} ${event.date} ${event.type}`.toLowerCase().includes(term))
  }, [timeline.events, search])
  const attach = useMutation({
    mutationFn: async () => {
      const result = await fetchAPI<{ added: number; already_attached: number }>(
        `/api/timeline/event-files?${new URLSearchParams({ case_id: caseId })}`,
        { method: "POST", body: { event_key: chosen, evidence_file_ids: files.map((file) => file.id) } }
      )
      setReceipt(result)
      await client.invalidateQueries({ queryKey: ["timeline-event-files", caseId] })
      onDone?.()
    },
  })
  const eventName = timeline.events.find((event) => event.key === chosen)?.name
  return (
    <Dialog open onOpenChange={(open) => { if (!open && !attach.isPending) onClose() }}>
      <DialogContent className="flex max-h-[85vh] max-w-2xl flex-col overflow-hidden">
        <DialogTitle>Add to event</DialogTitle>
        <DialogDescription>
          {files.length} selected file{files.length === 1 ? "" : "s"} · Attach to an event on this case’s Timeline.
          The event stays as it is.
        </DialogDescription>
        {receipt ? (
          <p role="status" className="font-semibold">
            {receipt.added} attached{eventName ? ` to “${eventName}”` : ""}.
            {receipt.already_attached > 0 && ` ${receipt.already_attached} were already attached.`}
          </p>
        ) : (
          <>
            <input
              type="search"
              aria-label="Find an event"
              placeholder="Find an event by name, date or type"
              className="rounded border bg-background p-2 text-sm"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
            {timeline.isLoading && <p className="text-sm text-muted-foreground">Loading events…</p>}
            {timeline.error && <p role="alert" className="text-destructive">{timeline.error.message}</p>}
            <ul className="min-h-0 flex-1 divide-y overflow-y-auto rounded border text-sm" role="listbox" aria-label="Events">
              {matches.slice(0, SHOWN).map((event) => (
                <li key={event.key}>
                  <button
                    type="button"
                    role="option"
                    aria-selected={chosen === event.key}
                    className={`w-full p-2 text-left hover:bg-muted ${chosen === event.key ? "bg-muted font-medium" : ""}`}
                    onClick={() => setChosen(event.key)}
                  >
                    {event.date} · {event.type} · {event.name}
                  </button>
                </li>
              ))}
            </ul>
            {matches.length > SHOWN && (
              <p className="text-xs text-muted-foreground">
                Showing the first {SHOWN} of {matches.length} events. Type to narrow the list.
              </p>
            )}
            {matches.length === 0 && !timeline.isLoading && <p className="text-sm">No event matches.</p>}
          </>
        )}
        {attach.error && <p role="alert" className="text-destructive">{(attach.error as Error).message}</p>}
        <footer className="flex shrink-0 gap-2 border-t pt-3">
          {!receipt && (
            <Button disabled={!chosen || attach.isPending} onClick={() => attach.mutate()}>
              {attach.isPending ? "Attaching…" : "Attach to this event"}
            </Button>
          )}
          <Button variant="outline" disabled={attach.isPending} onClick={onClose}>
            {receipt ? "Done" : "Cancel"}
          </Button>
        </footer>
      </DialogContent>
    </Dialog>
  )
}
