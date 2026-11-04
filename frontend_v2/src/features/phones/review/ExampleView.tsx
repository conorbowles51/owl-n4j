import { instantWords } from "../lib/time-words"
import { fmt } from "../ui/count-sentence"
import type { ExampleKind } from "./readings.api"

const ZONE = "UTC"

function roleWords(role: string | null) {
  return role ? role.replace(/_/g, " ") : "side not known"
}

export function ExampleView({ k }: { k: ExampleKind }) {
  const x = k.example
  return (
    <div className="mt-2 flex flex-col gap-1 rounded border bg-background p-2 text-sm">
      <p className="text-xs text-muted-foreground">
        {k.label}. {fmt(k.count)} of the affected records are of this kind.
      </p>
      <p>{x.instant ? instantWords(x.instant, ZONE) : "No time recorded"}{x.app ? ` · ${x.app}` : ""}{x.direction ? ` · ${x.direction}` : ""}</p>
      {x.parties.length > 0 && (
        <ul className="flex flex-col gap-0.5">
          {x.parties.map((p, i) => (
            <li key={i} className={p.mapped_by_this ? "font-medium" : undefined}>
              {p.implicit_owner ? "The phone's owner" : p.name || p.identifier || "No name or number"}
              {!p.implicit_owner && p.name && p.identifier ? ` (${p.identifier})` : ""}: read as {roleWords(p.role)}
              {p.mapped_by_this ? " (this reading)" : ""}
            </li>
          ))}
        </ul>
      )}
      {x.times.filter((t) => t.mapped_by_this || t.is_event_time).map((t, i) => (
        <p key={i} className={t.mapped_by_this ? "font-medium" : undefined}>
          {t.field}: {t.instant ? instantWords(t.instant, ZONE) : t.original_text ?? "no time"}
          {t.mapped_by_this ? " (this reading)" : ""}
        </p>
      ))}
      {x.subject && <p>Subject: {x.subject}</p>}
      {(x.kind === "message" || x.kind === "email") && (
        <p className="whitespace-pre-wrap rounded bg-muted/40 p-1">{x.text || <em>No text in this record</em>}</p>
      )}
      {!x.kind && x.title && <p>{x.title}</p>}
      {x.deleted_state && x.deleted_state !== "Intact" && <p>Marked on the phone as: {x.deleted_state}</p>}
    </div>
  )
}
