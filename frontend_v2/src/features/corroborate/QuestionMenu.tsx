import { useEffect, useState } from "react"
import { useNavigate } from "react-router-dom"
import { useQuery } from "@tanstack/react-query"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { relationAPI, setCurrentQuery } from "@/features/relations/api"
import { corroborateAPI, type QuestionChips, type SuggestedQuestion } from "./api"
import { selectionMembers, useSelection } from "./selection-store"

const CHIP_WORDS: Record<keyof QuestionChips, string> = { when: "When", nights: "Nights", who: "Who", what: "What", compare_with: "Compare with" }

/**
 * The question menu and composer (lx-corroselect E). It reads the whole selection, says what Loupe takes from it, offers
 * three to five questions each with its count, and shows the chosen question as editable chips. Loupe picks what to
 * compare with and shows it; the person can change it. Corroborate saves the whole selection as one group and runs it.
 */
export function QuestionMenu({ caseId, onClose }: { caseId: string; onClose: () => void }) {
  const parts = useSelection(caseId)
  const members = selectionMembers(parts)
  const key = members.map((m) => `${m.type}:${m.id}`).join("|")
  const navigate = useNavigate()
  const preview = useQuery({ queryKey: ["corroborate-preview", caseId, key], queryFn: () => corroborateAPI.preview(caseId, members), enabled: members.length > 0, staleTime: 30_000 })
  const [picked, setPicked] = useState<SuggestedQuestion | null>(null)
  const [chips, setChips] = useState<QuestionChips | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    if (preview.data && !picked && preview.data.questions.length) {
      setPicked(preview.data.questions[0])
      setChips(preview.data.questions[0].chips)
    }
  }, [preview.data, picked])
  const choose = (q: SuggestedQuestion) => {
    setPicked(q)
    setChips(q.chips)
  }
  const run = async () => {
    if (!picked || !chips) return
    setBusy(true)
    setError(null)
    try {
      const made = await relationAPI.create(caseId, { members, surface: "corroborate", question: { kind: picked.kind, text: picked.text, chips } })
      setCurrentQuery(caseId, { id: made.group.id, count: made.group.member_count })
      onClose()
      navigate(`/cases/${caseId}/relations/${made.group.id}`)
    } catch (e) {
      setError(e instanceof Error ? e.message : "Corroborate could not start. Nothing was saved.")
    } finally {
      setBusy(false)
    }
  }
  const d = preview.data
  return (
    <Dialog open onOpenChange={(o) => !o && !busy && onClose()}>
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle>Corroborate</DialogTitle>
          <DialogDescription>Pick the question. Loupe checks every kind of record that applies. The records show what occurs together, not why.</DialogDescription>
        </DialogHeader>
        {members.length === 0 && <p className="text-sm">Nothing is selected.</p>}
        {preview.isLoading && <p role="status" className="text-sm">Reading {members.length.toLocaleString("en-US")} selected items…</p>}
        {preview.isError && <p role="alert" className="text-sm text-destructive">The selection could not be read. Nothing was changed.</p>}
        {d && (
          <div className="flex flex-col gap-3 text-sm">
            <div>
              <p className="font-medium">What Loupe takes from your {d.members.toLocaleString("en-US")} items</p>
              <ul className="list-disc pl-5">
                <li>People: {d.taken.people.length ? d.taken.people.slice(0, 6).map((p) => p.label).join(", ") + (d.taken.people.length > 6 ? ` and ${d.taken.people.length - 6} more` : "") : "none named"}</li>
                <li>Times: {d.taken.times.from ? `${d.taken.times.from} to ${d.taken.times.to} (${d.taken.times.dated} dated${d.taken.times.undated ? `, ${d.taken.times.undated} undated` : ""})` : "no dates in the selection"}</li>
                <li>Places: {d.taken.places.length ? d.taken.places.slice(0, 4).map((p) => `${p.label} (${p.count})`).join(", ") : "none"}</li>
                <li>Items: {d.taken.items.map((i) => i.words).join(", ")}</li>
              </ul>
              {d.left_out.count > 0 && <p role="status">{d.left_out.count.toLocaleString("en-US")} chosen items are not in this case and are left out.</p>}
            </div>
            <div role="radiogroup" aria-label="Questions" className="flex flex-col gap-1">
              {d.questions.map((q) => (
                <label key={q.kind} className="flex cursor-pointer items-start gap-2 rounded border px-2 py-1 has-[:checked]:border-primary has-[:checked]:bg-primary/10">
                  <input type="radio" name="corro-question" checked={picked?.kind === q.kind} onChange={() => choose(q)} />
                  <span>{q.text} <span className="text-muted-foreground">· {q.count_words}</span></span>
                </label>
              ))}
            </div>
            {picked && chips && (
              <div className="flex flex-col gap-1">
                <p className="font-medium">Your question: {picked.text}</p>
                <div className="grid grid-cols-1 gap-1 sm:grid-cols-2">
                  {(Object.keys(CHIP_WORDS) as (keyof QuestionChips)[]).map((k) => (
                    <label key={k} className="flex flex-col text-xs text-muted-foreground">
                      {CHIP_WORDS[k]}
                      <input className="rounded border bg-card px-2 py-1 text-sm text-foreground" value={chips[k]} onChange={(e) => setChips({ ...chips, [k]: e.target.value })} />
                    </label>
                  ))}
                </div>
                <p className="text-xs text-muted-foreground">Loupe chose what to compare with; change it if you know better.</p>
              </div>
            )}
          </div>
        )}
        {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
        <DialogFooter className="gap-2">
          <Button disabled={busy || !picked} onClick={() => void run()}>{busy ? "Starting…" : "Corroborate"}</Button>
          <Button variant="ghost" disabled={busy} onClick={onClose}>Cancel</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
