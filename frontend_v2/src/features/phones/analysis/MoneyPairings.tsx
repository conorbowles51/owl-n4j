import { useState } from "react"
import { Link } from "react-router-dom"
import { useMutation } from "@tanstack/react-query"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { moneyAPI, type PairDecision, type PairLevel, type Pairing } from "./money-api"
import { amountWords } from "./money-words"

/**
 * 05 section 4.3.8: every payment in the financial records that could be a phone money reading, strongest first, with
 * its strength by rule (how well matched, how substantiated) and a person's confirm or reject, remembered across
 * reruns. A rule-found match never reads as confirmed; a rejected one stays visible, collapsed, and is not counted.
 */
const LEVEL_WORDS: Record<PairLevel, string> = { strong: "Strong", moderate: "Moderate", weak: "Weak", faint: "Faint" }
const LEVEL_CLASS: Record<PairLevel, string> = {
  strong: "border-emerald-600 text-emerald-800",
  moderate: "border-sky-600 text-sky-800",
  weak: "border-amber-600 text-amber-800",
  faint: "border-slate-400 text-slate-600",
}

export function LevelBadge({ level }: { level: PairLevel }) {
  return <span className={`rounded border px-1 text-xs ${LEVEL_CLASS[level]}`} data-testid="pair-level">{LEVEL_WORDS[level]}</span>
}

function PairRow({ caseId, recordUid, fieldPath, p, canEdit, onChanged }: {
  caseId: string; recordUid: string; fieldPath: string; p: Pairing; canEdit: boolean; onChanged: () => void
}) {
  const [note, setNote] = useState("")
  const [noting, setNoting] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const m = useMutation({
    mutationFn: (d: PairDecision | "undo") => moneyAPI.decidePair(caseId, recordUid, fieldPath, p.transaction_id, d, note.trim()),
    onSuccess: () => { setNote(""); setNoting(false); setErr(null); onChanged() },
    onError: (e) => setErr(String((e as Error).message || e)),
  })
  const amount = p.amount_minor != null && p.currency ? amountWords({ amount_minor: p.amount_minor, currency: p.currency }) : null
  const body = (
    <div className="space-y-1">
      <div className="flex flex-wrap items-baseline gap-2">
        <LevelBadge level={p.level} />
        <Link className="underline" to={`/cases/${caseId}/financial?view=transactions&payment=${p.transaction_id}`}>
          Payment {p.ref_id ?? ""}
        </Link>
        {amount && <span>{amount}</span>}
        {p.date && <span className="text-muted-foreground">{p.date}</span>}
        <span className="text-xs" data-testid="pair-status">{p.decision_words ?? p.rule_words}</span>
      </div>
      {p.reasons.match.length > 0 && <p className="text-xs" data-testid="pair-matched">How well matched: {p.reasons.match.join("; ")}.</p>}
      {p.reasons.substantiation.length > 0 && (
        <p className="text-xs" data-testid="pair-substantiated">
          Substantiated by {p.reasons.substantiation.length} {p.reasons.substantiation.length === 1 ? "source" : "sources"}: {p.reasons.substantiation.join("; ")}.
        </p>
      )}
      {p.base_rate && <p className="text-xs" data-testid="pair-base-rate">{p.base_rate.words}</p>}
      {canEdit && (
        <div className="flex flex-wrap items-center gap-2">
          {p.decision !== "confirmed" && p.found_by_rule && (
            <Button size="sm" variant="outline" aria-label={`Confirm the match with payment ${p.ref_id ?? ""}`.trim()} disabled={m.isPending} onClick={() => m.mutate("confirmed")}>Confirm</Button>
          )}
          {p.decision !== "rejected" && p.found_by_rule && (
            <Button size="sm" variant="outline" aria-label={`Reject the match with payment ${p.ref_id ?? ""}`.trim()} disabled={m.isPending} onClick={() => m.mutate("rejected")}>Reject</Button>
          )}
          {p.decision && <Button size="sm" variant="outline" aria-label={`Undo the decision on payment ${p.ref_id ?? ""}`.trim()} disabled={m.isPending} onClick={() => m.mutate("undo")}>Undo</Button>}
          {!noting && !p.decision && <button className="text-xs underline" onClick={() => setNoting(true)}>Add a note</button>}
        </div>
      )}
      {canEdit && noting && (
        <Textarea aria-label="Note" value={note} onChange={(e) => setNote(e.target.value)} className="h-12 text-xs" placeholder="Optional note, kept with your decision" />
      )}
      {err && <p role="alert" className="text-xs text-destructive">{err}</p>}
    </div>
  )
  if (p.decision === "rejected") {
    return (
      <li data-testid="money-pair" data-decision="rejected" className="text-xs text-muted-foreground">
        <details>
          <summary>{p.decision_words}. Not counted.</summary>
          {body}
        </details>
      </li>
    )
  }
  return <li data-testid="money-pair" data-decision={p.decision ?? "none"} className="text-sm">{body}</li>
}

export function MoneyPairings({ caseId, recordUid, fieldPath, pairings, leftOut, canEdit, onChanged }: {
  caseId: string; recordUid: string; fieldPath: string; pairings: Pairing[]; leftOut?: string | null; canEdit: boolean; onChanged: () => void
}) {
  if (!pairings.length && !leftOut) return null
  const live = pairings.filter((p) => p.decision !== "rejected")
  return (
    <div className="mt-1 space-y-1" aria-label="Payments that could be this one">
      <p className="text-xs font-medium">
        {live.length === 0 ? "No payment in the financial records is a candidate." :
          `${live.length} ${live.length === 1 ? "payment" : "payments"} in the financial records could be this one, strongest first.`}
      </p>
      <ul className="space-y-2 border-l pl-2">
        {pairings.map((p) => (
          <PairRow key={p.transaction_id} caseId={caseId} recordUid={recordUid} fieldPath={fieldPath} p={p} canEdit={canEdit} onChanged={onChanged} />
        ))}
      </ul>
      {leftOut && <p className="text-xs text-muted-foreground" data-testid="pair-left-out">{leftOut}</p>}
    </div>
  )
}
