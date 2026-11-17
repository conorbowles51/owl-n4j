import { useEffect, useState } from "react"
import { Button } from "@/components/ui/button"
import { answerRatingsAPI, type AnswerRating as Rating, type AnswerRatingKind, type AnswerSource } from "../answer-ratings-api"

const KINDS: { kind: AnswerRatingKind; label: string; hint: string }[] = [
  { kind: "missed_something", label: "Missed something", hint: "The answer left out something the case holds." },
  { kind: "not_relevant", label: "Not relevant", hint: "The answer is about the wrong thing." },
  { kind: "too_thin", label: "Too thin", hint: "The answer is too short or too shallow for the question." },
]

/** lx-agenttools D20: a person tells the system an answer missed something, was not relevant, or was too thin.
 * Each rating is stored with the answer's run and becomes a test of the agent's relevance. */
export function AnswerRating({
  caseId,
  messageId,
  source = "agent",
}: {
  caseId: string
  messageId: string
  source?: AnswerSource
}) {
  const [active, setActive] = useState<Rating[]>([])
  const [open, setOpen] = useState<AnswerRatingKind | null>(null)
  const [note, setNote] = useState("")
  const [record, setRecord] = useState("")
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let live = true
    answerRatingsAPI
      .list(messageId, source)
      .then((r) => live && setActive(r.ratings))
      .catch(() => undefined)
    return () => {
      live = false
    }
  }, [messageId, source])

  const send = async (kind: AnswerRatingKind, withdraw: boolean) => {
    setBusy(true)
    setError(null)
    try {
      const r = await answerRatingsAPI.rate(caseId, messageId, {
        kind,
        note: withdraw ? "" : note,
        recordRef: withdraw || kind !== "missed_something" ? undefined : record,
        withdraw,
        source,
      })
      setActive(r.ratings)
      setOpen(null)
      setNote("")
      setRecord("")
    } catch (e) {
      setError(e instanceof Error ? e.message : "The rating could not be saved.")
    } finally {
      setBusy(false)
    }
  }

  const has = (kind: AnswerRatingKind) => active.some((r) => r.kind === kind)
  return (
    <div className="mt-1 text-xs" aria-label="Rate this answer" data-guide="agent-rate">
      <div className="flex flex-wrap items-center gap-1">
        <span className="text-muted-foreground">Rate this answer:</span>
        {KINDS.map(({ kind, label, hint }) => (
          <Button
            key={kind}
            type="button"
            size="sm"
            variant={has(kind) ? "secondary" : "ghost"}
            className="h-6 px-2 text-xs"
            title={hint}
            aria-pressed={has(kind)}
            disabled={busy}
            onClick={() => (has(kind) ? void send(kind, true) : setOpen(open === kind ? null : kind))}
          >
            {label}
          </Button>
        ))}
      </div>
      {open && (
        <div className="mt-1 flex max-w-xl flex-col gap-1 rounded border p-2" aria-label={`Rate as ${open}`}>
          <label className="flex flex-col gap-0.5">
            What went wrong (optional)
            <textarea
              className="rounded border bg-background p-1"
              rows={2}
              maxLength={2000}
              value={note}
              onChange={(e) => setNote(e.target.value)}
            />
          </label>
          {open === "missed_something" && (
            <label className="flex flex-col gap-0.5">
              A record that should have been found (optional rec://, txn:// or doc:// link)
              <input
                className="rounded border bg-background p-1"
                value={record}
                maxLength={400}
                onChange={(e) => setRecord(e.target.value)}
              />
            </label>
          )}
          <div className="flex gap-1">
            <Button type="button" size="sm" disabled={busy} onClick={() => void send(open, false)}>
              Send rating
            </Button>
            <Button type="button" size="sm" variant="ghost" disabled={busy} onClick={() => setOpen(null)}>
              Cancel
            </Button>
          </div>
        </div>
      )}
      {active.length > 0 && (
        <p role="status" className="mt-0.5 text-muted-foreground">
          Rated: {active.map((r) => r.label).join(", ")}. Select a rating again to withdraw it.
        </p>
      )}
      {error && <p role="alert">{error}</p>}
    </div>
  )
}
