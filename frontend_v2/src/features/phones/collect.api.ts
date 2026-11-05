import { fetchAPI } from "@/lib/api-client"

/**
 * Collecting phone material into Loupe's existing case-building system (07 section 6) through lx-collect's
 * routes: dossier links (POST /api/dossiers/{id}/links:add) and Workspace entry links for findings, theories,
 * notes and labels (POST /api/workspace/{case}/entries/{id}/links:batch). Each request carries at most
 * PART_SIZE links (the routes refuse more, never cut), so larger selections are sent in stated parts.
 */
export type TargetKind = "dossier" | "finding" | "theory" | "note" | "timeline" | "label"

export interface CollectTarget {
  kind: TargetKind
  id: string
  label: string
  recent?: boolean
  /** A linked person's dossier is offered first (07 J-12). */
  linkedPerson?: boolean
}

export type Relationship = "unclassified" | "supports" | "contradicts" | "context"
export type DossierRole = "link" | "contact" | "photo" | "assessment_support" | "interview_evidence"

export interface CollectLink {
  target_type: "phone_record" | "phone_thread" | "phone_file" | "phone_identity" | "phone_extraction" | "phone_selection" | "phone_view" | "phone_analysis" | "statement_check"
  target_id: string
  label?: string
  source_anchor: Record<string, unknown>
}

export interface CollectResult {
  added: number
  skipped: number
  refused: number
  refusedReason?: string
  /** The links this add created (not the ones already there), so Undo removes only those. */
  linkIds?: string[]
  /** A Workspace entry's version after the add; each removal names the version it expects. */
  version?: number
}

export interface CollectClient {
  add(caseId: string, target: CollectTarget, links: CollectLink[], opts: { relationship: Relationship; role: DossierRole; origin: string }): Promise<CollectResult>
}

export const PART_SIZE = 5_000

export function partsNeeded(n: number): number {
  return Math.ceil(n / PART_SIZE)
}

export async function addInParts(
  client: CollectClient,
  caseId: string,
  target: CollectTarget,
  links: CollectLink[],
  opts: { relationship: Relationship; role: DossierRole; origin: string },
  onProgress?: (done: number, total: number) => void,
  onPart?: (sent: number, sofar: CollectResult) => void
): Promise<CollectResult> {
  const out: CollectResult = { added: 0, skipped: 0, refused: 0 }
  onProgress?.(0, links.length)
  for (let i = 0; i < links.length; i += PART_SIZE) {
    const part = links.slice(i, i + PART_SIZE)
    const r = await client.add(caseId, target, part, opts)
    out.added += r.added
    out.skipped += r.skipped
    out.refused += r.refused
    if (r.refusedReason) out.refusedReason = r.refusedReason
    if (r.linkIds) out.linkIds = [...(out.linkIds ?? []), ...r.linkIds]
    if (r.version !== undefined) out.version = r.version
    onProgress?.(Math.min(links.length, i + part.length), links.length)
    onPart?.(Math.min(links.length, i + part.length), out)
  }
  return out
}

/** The noun for a count: "1 message", "2 messages" ("records (messages and their attachments)" -> "record (...)"). */
export function countNoun(n: number, noun: string): string {
  return n === 1 ? noun.replace(/^(\w+?)s\b/, "$1") : noun
}

export function resultSentence(r: CollectResult, noun: string, target: CollectTarget): string {
  const s = [`Added ${r.added.toLocaleString("en-US")} ${countNoun(r.added, noun)} to ${target.label}.`]
  if (r.skipped) s.push(`${r.skipped.toLocaleString("en-US")} ${r.skipped === 1 ? "was" : "were"} already there.`)
  if (r.refused) s.push(`${r.refused.toLocaleString("en-US")} could not be added${r.refusedReason ? `: ${r.refusedReason}` : ""}.`)
  return s.join(" ")
}

export const liveCollectClient: CollectClient = {
  async add(caseId, target, links, opts) {
    if (target.kind === "dossier") {
      const r = await fetchAPI<{ added: number; skipped: number; added_link_ids?: string[] }>(`/api/dossiers/${target.id}/links:add`, {
        method: "POST",
        body: { links: links.map((l) => ({ target_type: l.target_type, target_id: l.target_id, label: l.label, relationship_type: opts.role, source_anchor: l.source_anchor })), origin: opts.origin },
      })
      return { added: r.added, skipped: r.skipped, refused: 0, linkIds: r.added_link_ids }
    }
    if (target.kind === "timeline") {
      // Add to Timeline gains phone records in lx-collect item 8; until then it is refused with this sentence.
      return { added: 0, skipped: 0, refused: links.length, refusedReason: "the Timeline does not take phone records yet" }
    }
    const r = await fetchAPI<{ added: number; skipped: number; added_link_ids?: string[]; version?: number }>(`/api/workspace/${caseId}/entries/${target.id}/links:batch`, {
      method: "POST",
      body: {
        links: links.map((l) => ({ target_type: l.target_type, target_id: l.target_id, target_label: l.label, relationship: opts.relationship, source_anchor: l.source_anchor })),
        rationale: opts.origin,
      },
    })
    return { added: r.added, skipped: r.skipped, refused: 0, linkIds: r.added_link_ids, version: r.version }
  },
}

/**
 * Undo an add: remove exactly the links that add created; links that were already there stay. Returns how many
 * were removed. A failure part way states how many were removed before it.
 */
export async function undoCollect(caseId: string, target: CollectTarget, result: CollectResult): Promise<number> {
  const ids = result.linkIds ?? []
  let version = result.version
  let removed = 0
  for (const id of ids) {
    try {
      if (target.kind === "dossier") {
        await fetchAPI(`/api/dossiers/${target.id}/links/${id}`, { method: "DELETE" })
      } else {
        const r = await fetchAPI<{ version: number }>(
          `/api/workspace/${caseId}/entries/${target.id}/links/${id}?expected_version=${version ?? 1}`,
          { method: "DELETE" },
        )
        version = r.version
      }
      removed += 1
    } catch (e) {
      const why = e instanceof Error ? e.message : "the request failed"
      throw new Error(`Undo stopped after removing ${removed.toLocaleString("en-US")} of ${ids.length.toLocaleString("en-US")}: ${why}`)
    }
  }
  return removed
}
