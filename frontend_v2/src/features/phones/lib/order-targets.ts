import type { CollectTarget, TargetKind } from "../collect.api"

/** Add to… lists a linked person's dossier first, then recent targets, then by name (07 6.2). */
export function orderTargets(targets: CollectTarget[], kind: TargetKind): CollectTarget[] {
  const of = targets.filter((t) => (kind === "finding" ? t.kind === "finding" || t.kind === "theory" : t.kind === kind))
  return [...of].sort((a, b) => Number(!!b.linkedPerson) - Number(!!a.linkedPerson) || Number(!!b.recent) - Number(!!a.recent) || a.label.localeCompare(b.label))
}
