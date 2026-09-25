import type { AgentArtifact } from "../types"

export function AgentArtifactNotes({ artifact }: { artifact: AgentArtifact }) {
  const notes = [
    ...new Set(
      [artifact.data.notes, artifact.metadata.notes]
        .filter(
          (value): value is string =>
            typeof value === "string" && !!value.trim()
        )
        .map((value) => value.trim())
    ),
  ]
  if (!notes.length) return null
  return (
    <section
      aria-label="Analysis scope and notes"
      tabIndex={0}
      className="mb-3 max-h-48 shrink-0 overflow-y-auto border-l-2 border-amber-500/70 pl-3 text-xs leading-5 text-muted-foreground [overflow-wrap:anywhere] focus-visible:outline focus-visible:outline-2"
    >
      <h4 className="font-semibold text-foreground">Scope and notes</h4>
      {notes.map((note) => (
        <p key={note} className="whitespace-pre-wrap">
          {note}
        </p>
      ))}
    </section>
  )
}
