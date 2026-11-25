import { useEffect, useState } from "react"
import { useNavigate } from "react-router-dom"
import { useQuery } from "@tanstack/react-query"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { setCurrentQuery } from "@/features/relations/api"
import { corroborateAPI, scopeIsEmpty, type ItemGroup, type QuestionChips, type Scope, type SuggestedQuestion } from "./api"
import { againstOthers } from "./group-runs"
import { GroupPicker } from "./GroupPicker"
import { ScopeBar } from "./ScopeBar"
import { selectionMembers, useSelection } from "./selection-store"

const CHIP_WORDS: Record<keyof QuestionChips, string> = { when: "When", nights: "Nights", who: "Who", what: "What", compare_with: "Compare with" }

/**
 * The question menu and composer (lx-corroselect E). It reads the whole selection, says what Loupe takes from it, offers
 * three to five questions each with its count, and shows the chosen question as editable chips. Loupe picks what to
 * compare with and shows it; the person can change it. Corroborate saves the whole selection as one group and runs it.
 */
export function QuestionMenu({ caseId, onClose, initialScope, draftedKind }: { caseId: string; onClose: () => void; initialScope?: Scope; /** A question the assistant drafted: it opens chosen, marked as the assistant's, and runs only when the person presses Corroborate. */ draftedKind?: string }) {
  const parts = useSelection(caseId)
  const members = selectionMembers(parts)
  const key = members.map((m) => `${m.type}:${m.id}`).join("|")
  const navigate = useNavigate()
  const [scope, setScope] = useState<Scope>(initialScope ?? {})
  const scopeKey = JSON.stringify(scope)
  const preview = useQuery({ queryKey: ["corroborate-preview", caseId, key, scopeKey], queryFn: () => corroborateAPI.preview(caseId, members, scopeIsEmpty(scope) ? undefined : scope), enabled: members.length > 0, staleTime: 30_000, placeholderData: (prev) => prev })
  const [picked, setPicked] = useState<SuggestedQuestion | null>(null)
  const [chips, setChips] = useState<QuestionChips | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const choose = (q: SuggestedQuestion) => {
    setPicked(q)
    setChips(q.comparison?.words ? { ...q.chips, compare_with: q.comparison.words } : q.chips)
  }
  useEffect(() => {
    if (preview.data && !picked && preview.data.questions.length) {
      choose(preview.data.questions.find((x) => x.kind === draftedKind) ?? preview.data.questions[0])
    }
  }, [preview.data, picked, draftedKind])
  const run = async () => {
    if (!picked || !chips) return
    setBusy(true)
    setError(null)
    try {
      // Inside the scope only: the preview named exactly which items are in it. The scope is kept with the question.
      const kept = preview.data?.scope.kept
      const keep = kept ? new Set(kept.map((k) => `${k.type}:${k.id}`)) : null
      const asked = keep ? members.filter((m) => keep.has(`${m.type}:${m.id}`)) : members
      const made = await corroborateAPI.run(caseId, { members: asked, surface: "corroborate", question: { kind: picked.kind, text: picked.text, chips: { ...chips, ...(preview.data?.scope.words.length ? { scope: preview.data.scope.words.join("; ") } : {}) } } })
      setCurrentQuery(caseId, { id: made.group.id, count: made.group.member_count })
      onClose()
      navigate(`/cases/${caseId}/corroborate?q=${made.group.id}`)
    } catch (e) {
      setError(e instanceof Error ? e.message : "Corroborate could not start. Nothing was saved.")
    } finally {
      setBusy(false)
    }
  }
  // One group asked about alone, or every group in turn, each against the others (group_vs_group in the engine).
  const [each, setEach] = useState<{ label: string; id: string }[]>([])
  const runGroups = async (runs: ItemGroup[], all: ItemGroup[]) => {
    if (!picked || !chips) return
    setBusy(true)
    setError(null)
    setEach([])
    const done: { label: string; id: string }[] = []
    try {
      for (const g of runs) {
        const made = await corroborateAPI.run(caseId, { members: g.members, surface: "corroborate", question: { kind: picked.kind, text: picked.text, chips: { ...chips, compare_with: "group_vs_group", against: againstOthers(all, g), group: g.label } } })
        done.push({ label: g.label, id: made.group.id })
        setEach([...done])
      }
      if (runs.length === 1) {
        setCurrentQuery(caseId, { id: done[0].id, count: runs[0].count })
        onClose()
        navigate(`/cases/${caseId}/corroborate?q=${done[0].id}`)
      }
    } catch (e) {
      setError(`${done.length ? `${done.length} of ${runs.length} groups ran. ` : ""}${e instanceof Error ? e.message : "Corroborate could not start."} Nothing else was changed.`)
    } finally {
      setBusy(false)
    }
  }
  const d = preview.data
  return (
    <Dialog open onOpenChange={(o) => !o && !busy && onClose()}>
      <DialogContent className="max-h-[90vh] max-w-xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Corroborate</DialogTitle>
          <DialogDescription>{draftedKind ? "The assistant drafted this question. Check it, change it if you want, then press Corroborate. Nothing has run. " : ""}Pick the question. Loupe checks every kind of record that applies. The records show what occurs together, not why.</DialogDescription>
        </DialogHeader>
        {members.length === 0 && <p className="text-sm">Nothing is selected.</p>}
        {preview.isLoading && <p role="status" className="text-sm">Reading {members.length.toLocaleString("en-US")} selected items…</p>}
        {preview.isError && <p role="alert" className="text-sm text-destructive">The selection could not be read. Nothing was changed.</p>}
        {d && (
          <div className="flex flex-col gap-3 text-sm">
            <div>
              <p className="font-medium">What Loupe takes from your {d.members.toLocaleString("en-US")} {d.members === 1 ? "item" : "items"}</p>
              <ul className="list-disc pl-5">
                <li>People: {d.taken.people.length ? d.taken.people.slice(0, 6).map((p) => p.label).join(", ") + (d.taken.people.length > 6 ? ` and ${d.taken.people.length - 6} more` : "") : "none named"}</li>
                <li>Times: {d.taken.times.from ? `${d.taken.times.from} to ${d.taken.times.to} (${d.taken.times.dated} dated${d.taken.times.undated ? `, ${d.taken.times.undated} undated` : ""})` : "no dates in the selection"}</li>
                <li>Places: {d.taken.places.length ? d.taken.places.slice(0, 4).map((p) => `${p.label} (${p.count})`).join(", ") : "none"}</li>
                <li>Items: {d.taken.items.map((i) => i.words).join(", ")}</li>
              </ul>
              {d.left_out.count > 0 && <p role="status">{d.left_out.count.toLocaleString("en-US")} chosen items are not in this case and are left out.</p>}
            </div>
            <ScopeBar caseId={caseId} scope={scope} onChange={(next) => { setScope(next); setPicked(null) }} preview={d} />
            <GroupPicker caseId={caseId} members={members} busy={busy} onGroup={(g, all) => void runGroups([g], all)} onEach={(runs, all) => void runGroups(runs, all)} />
            {each.length > 0 && (
              <ul className="text-xs" aria-label="Group results">
                {each.map((r) => <li key={r.id}>{r.label}: <a className="underline" href={`/cases/${caseId}/corroborate?q=${r.id}`}>open the result</a></li>)}
              </ul>
            )}
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
                {picked.checks && picked.checks.length > 0 && <p className="text-xs text-muted-foreground">Loupe will check: {picked.checks.map((c) => c.words).join(", ")}.</p>}
                <p className="text-xs text-muted-foreground">Loupe chose what to compare with{picked.comparison ? ` (${picked.comparison.count.toLocaleString("en-US")} ordinary instances)` : ""}; change it if you know better.</p>
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
