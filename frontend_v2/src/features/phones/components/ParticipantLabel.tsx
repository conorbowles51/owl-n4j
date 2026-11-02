import { identifierText, labelText } from "../lib/labels"
import type { ParticipantLabelData } from "../schemas"

/**
 * One participant as 03 section 3.3 writes it: a name (or "(no name on this phone)") and an identifier (or the
 * owner form). The text is the same as the server's ``labels.label_text`` so the row, copy and export agree.
 */

export function ParticipantLabel({ label, onClick }: { label: ParticipantLabelData | null; onClick?: (l: ParticipantLabelData) => void }) {
  if (!label) return <span className="text-muted-foreground">(sender not recorded)</span>
  const ident = identifierText(label.identifier)
  const caseHover = label.case_names.length ? label.case_names.map((n) => `${n.phone_label}: ${n.name}`).join("; ") : undefined
  const captured = label.identifier?.captured && label.identifier.captured !== label.identifier.display ? `In the report: ${label.identifier.captured}` : undefined
  const notRecognised = label.identifier && label.identifier.normalised === false ? "Not a recognised number format" : undefined
  const title = [caseHover, captured, notRecognised].filter(Boolean).join(". ") || undefined
  const text = labelText(label)
  const inner = (
    <span title={title} data-participant={label.identity_key ?? ""}>
      {text}
      {label.name_basis === "case_person" && <span className="ml-1 rounded-sm bg-muted px-1 text-[10px] text-muted-foreground">Case name</span>}
      {!ident && !label.is_owner && <span className="sr-only"> no identifier recorded</span>}
    </span>
  )
  if (!onClick) return inner
  return (
    <button type="button" className="text-left hover:underline" onClick={() => onClick(label)}>
      {inner}
    </button>
  )
}

/** "→" on screen, read as "to"; "->" in copied text (D-10). */
export function Arrow() {
  return (
    <span aria-label="to" role="img" className="mx-1 text-muted-foreground">
      →
    </span>
  )
}
