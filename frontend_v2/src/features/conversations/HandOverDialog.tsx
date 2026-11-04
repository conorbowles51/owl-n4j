import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useState } from "react"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { caseMembersAPI } from "@/features/cases/members-api"
import { handOverReview, shareFailure, type HandedOver } from "@/features/phones/review-share"

/**
 * Hand over on a review task (07 J-15 step 4): reassigns the task and attaches a Workspace note, linked to it, that
 * lists the positions and open items. Only people who can do the review are offered; the server refuses anyone else,
 * and says why.
 */
export function HandOverDialog({ caseId, taskId, title, open, onClose }: { caseId: string; taskId: string; title: string; open: boolean; onClose: () => void }) {
  const qc = useQueryClient()
  const membersQ = useQuery({ queryKey: ["case-members", caseId], queryFn: () => caseMembersAPI.list(caseId), enabled: open && !!caseId })
  const members = (membersQ.data ?? []).filter((m) => m.preset !== "viewer")
  const [who, setWho] = useState("")
  const [note, setNote] = useState("")
  const [done, setDone] = useState<HandedOver | null>(null)
  const [error, setError] = useState<string | null>(null)
  const send = useMutation({
    mutationFn: () => handOverReview(caseId, taskId, who, note),
    onSuccess: (out) => {
      setDone(out)
      setError(null)
      void qc.invalidateQueries({ queryKey: ["phone-thread-review"] })
      void qc.invalidateQueries({ queryKey: ["phone-review-coverage"] })
      void qc.invalidateQueries({ queryKey: ["phone-continue-reading"] })
      void qc.invalidateQueries({ queryKey: ["phone-reading-rechecks"] })
      void qc.invalidateQueries({ queryKey: ["work", caseId] })
    },
    onError: (e) => setError(shareFailure(e, "The task could not be handed over.")),
  })
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Hand over</DialogTitle>
          <DialogDescription>{title}</DialogDescription>
        </DialogHeader>
        {done ? (
          <p role="status" className="text-sm">{done.words}</p>
        ) : (
          <div className="flex flex-col gap-2 text-sm">
            <label className="flex flex-col gap-1">
              Hand over to
              <select aria-label="Hand over to" className="h-8 rounded border bg-background px-2" value={who} onChange={(e) => setWho(e.target.value)}>
                <option value="">Choose a person</option>
                {members.map((m) => <option key={m.user_id} value={m.user_id}>{m.user_name || m.user_email}</option>)}
              </select>
            </label>
            {membersQ.isSuccess && members.length < 2 && <p role="status">You are the only person on this case who can do this review.</p>}
            <label className="flex flex-col gap-1">
              Anything to add (optional)
              <textarea aria-label="Anything to add" className="rounded border bg-background px-2 py-1" rows={3} maxLength={4000} value={note} onChange={(e) => setNote(e.target.value)} />
            </label>
            <p className="text-xs text-muted-foreground">A note linked to this task will list where reading stopped and what is still open.</p>
            {error && <p role="alert">{error}</p>}
          </div>
        )}
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>{done ? "Close" : "Cancel"}</Button>
          {!done && <Button disabled={!who || send.isPending} onClick={() => send.mutate()}>Hand over</Button>}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
