import type { CheckVerdict, MentionOutcome } from "./api"

/** Outcome and verdict pills, through the theme's status tokens (light and dark), as in the approved design. */
export function outcomeTone(o: MentionOutcome | null | undefined): string {
  switch (o) {
    case "fits_strongly":
      return "border-status-success/40 bg-status-success-soft text-status-success"
    case "fits_weakly":
      return "border-status-success/25 bg-status-success-soft/60 text-status-success"
    case "contradicts":
      return "border-status-error/40 bg-status-error-soft text-status-error"
    case "contradicts_weakly":
      return "border-status-error/25 bg-status-error-soft/60 text-status-error"
    default:
      return "border-border bg-muted text-muted-foreground"
  }
}

export function verdictText(v: CheckVerdict): string {
  if (v === "fits" || v === "fits_weakly") return "text-status-success"
  if (v === "contradicts" || v === "contradicts_weakly") return "text-status-error"
  return "text-muted-foreground"
}

export function outcomeHeadline(o: MentionOutcome | null | undefined): string {
  if (o === "fits_strongly" || o === "fits_weakly") return "text-status-success"
  if (o === "contradicts" || o === "contradicts_weakly") return "text-status-error"
  return "text-foreground"
}
