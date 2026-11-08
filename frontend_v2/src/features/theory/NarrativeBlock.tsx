import { Fragment, useState } from "react"
import { useQueryClient } from "@tanstack/react-query"
import { Button } from "@/components/ui/button"
import { theoryAPI, type Citation, type Narrative } from "./api"

/**
 * One narrative: what an addition shows (or how a theory fits together). A model reading carries the model's name
 * and "not confirmed" until a person confirms it; its marks ([m3]) show the member they cite. A person can confirm
 * it, replace it with their own words, or ask the model again; every earlier version stays readable (rule 1).
 */
export function NarrativeText({ narrative }: { narrative: Narrative }) {
  const byMark = new Map<string, Citation>(narrative.citations.map((c) => [c.mark, c]))
  const parts = narrative.text.split(/(\[(?:m|a)\d+\])/g)
  return (
    <p className="whitespace-pre-wrap text-sm">
      {parts.map((part, i) => {
        const mark = /^\[((?:m|a)\d+)\]$/.exec(part)?.[1]
        const cite = mark ? byMark.get(mark) : undefined
        if (!mark) return <Fragment key={i}>{part}</Fragment>
        return (
          <span
            key={i}
            className={`mx-0.5 rounded px-1 text-xs ${cite ? "bg-muted" : "bg-status-error/10 line-through"}`}
            title={cite ? cite.label : "This mark names nothing the model was given"}
          >
            {cite ? cite.label.slice(0, 40) : part}
          </span>
        )
      })}
    </p>
  )
}

export function NarrativeLabel({ narrative }: { narrative: Narrative }) {
  const model = narrative.origin === "agent"
  const read = narrative.basis?.read
  const of = narrative.basis?.of
  return (
    <p className={`text-xs ${model && !narrative.confirmed_by ? "text-status-review" : "text-muted-foreground"}`}>
      {narrative.words}
      {model && narrative.asked_by && ` · asked by ${narrative.asked_by}`}
      {narrative.created_at && ` · ${new Date(narrative.created_at).toLocaleString()}`}
      {model && read !== undefined && of !== undefined && read < of && ` · read ${read.toLocaleString("en-US")} of ${of.toLocaleString("en-US")} items`}
      {model && !!narrative.basis?.invalid_citations && ` · ${narrative.basis.invalid_citations} mark(s) named nothing it was given`}
    </p>
  )
}

export function NarrativeBlock({
  caseId,
  entryId,
  linkId,
  narrative,
  versions,
  history,
  emptyWords,
}: {
  caseId: string
  entryId: string
  /** null: the theory's own "how it fits together". */
  linkId: string | null
  narrative: Narrative | null
  versions: number
  /** Every version, newest first, when the caller has them (the Loupe). */
  history?: Narrative[]
  emptyWords: string
}) {
  const qc = useQueryClient()
  const [editing, setEditing] = useState(false)
  const [text, setText] = useState("")
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [showHistory, setShowHistory] = useState(false)
  const refresh = () => {
    void qc.invalidateQueries({ queryKey: ["theory-reading", caseId, entryId] })
    void qc.invalidateQueries({ queryKey: ["theory-loupe", caseId, entryId] })
  }
  const run = async (what: string, fn: () => Promise<unknown>) => {
    setBusy(what)
    setError(null)
    try {
      await fn()
      refresh()
      setEditing(false)
    } catch (e) {
      setError(e instanceof Error ? e.message : "That did not work")
    } finally {
      setBusy(null)
    }
  }
  const earlier = (history ?? []).filter((h) => h.id !== narrative?.id)
  return (
    <div className="flex flex-col gap-1 rounded border-l-2 border-muted pl-2">
      {narrative ? (
        <>
          <NarrativeText narrative={narrative} />
          <NarrativeLabel narrative={narrative} />
        </>
      ) : (
        <p className="text-sm text-muted-foreground">{emptyWords}</p>
      )}
      {editing ? (
        <div className="flex flex-col gap-1">
          <textarea className="min-h-20 rounded border bg-card px-2 py-1 text-sm" value={text} maxLength={8000} onChange={(e) => setText(e.target.value)} />
          <div className="flex gap-1">
            <Button size="sm" disabled={!text.trim() || !!busy} onClick={() => void run("Saving…", () => theoryAPI.write(caseId, entryId, linkId, text))}>
              Save as mine
            </Button>
            <Button size="sm" variant="outline" onClick={() => setEditing(false)} disabled={!!busy}>
              Cancel
            </Button>
          </div>
          {narrative && <p className="text-xs text-muted-foreground">The earlier version stays readable under Earlier versions.</p>}
        </div>
      ) : (
        <div className="flex flex-wrap gap-1">
          {narrative?.origin === "agent" && !narrative.confirmed_by && (
            <Button size="sm" variant="outline" disabled={!!busy} onClick={() => void run("Confirming…", () => theoryAPI.confirm(caseId, entryId, narrative.id))}>
              Confirm the model's reading
            </Button>
          )}
          <Button size="sm" variant="outline" disabled={!!busy} onClick={() => (setText(narrative?.text.replace(/\[(?:m|a)\d+\]/g, "").replace(/ {2,}/g, " ") ?? ""), setEditing(true))}>
            {narrative ? "Edit or replace" : "Write it"}
          </Button>
          <Button size="sm" variant="outline" disabled={!!busy} onClick={() => void run("The model is reading…", () => theoryAPI.infer(caseId, entryId, linkId))}>
            {narrative ? "Ask the model again" : "Ask the model"}
          </Button>
          {(versions > 1 || earlier.length > 0) && (history ? (
            <Button size="sm" variant="ghost" onClick={() => setShowHistory((v) => !v)}>
              Earlier versions ({earlier.length})
            </Button>
          ) : (
            <span className="self-center text-xs text-muted-foreground">{versions - 1} earlier version(s): view through the Loupe</span>
          ))}
        </div>
      )}
      {busy && <p role="status" className="text-xs">{busy}</p>}
      {error && <p role="alert" className="text-xs text-status-error">{error}</p>}
      {showHistory && earlier.length > 0 && (
        <ol className="flex flex-col gap-2 border-t pt-1" aria-label="Earlier versions">
          {earlier.map((h) => (
            <li key={h.id} className="opacity-80">
              <NarrativeText narrative={h} />
              <NarrativeLabel narrative={h} />
            </li>
          ))}
        </ol>
      )}
    </div>
  )
}
