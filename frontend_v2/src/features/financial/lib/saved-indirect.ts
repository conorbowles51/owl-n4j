import type { CaseworkLink } from "@/features/workspace/casework-api"
import {
  indirectCatalog,
  indirectEnvelope,
  indirectRequest,
  verifyIndirectReview,
  type IndirectCatalog,
} from "./indirect-review"

export const indirectWorkpaperSchema = "loupe.financial.indirect_workpaper/1"

// Older notes have the envelope but no method snapshot. Validate those against
// the current catalog; never invent missing historical definitions.
export async function readSavedIndirect(
  link: CaseworkLink,
  links: CaseworkLink[],
  caseId: string,
  loadCatalog: () => Promise<IndirectCatalog>
) {
  if (
    link.case_id !== caseId ||
    link.metadata.schema !== indirectWorkpaperSchema
  )
    throw Error("This workpaper does not belong to the selected case.")
  const envelope = indirectEnvelope.parse(link.metadata.envelope)
  if (envelope.case_id !== caseId)
    throw Error("This workpaper does not belong to the selected case.")
  if (new TextEncoder().encode(envelope.scenario_json).length > 1024 * 1024)
    throw Error("The saved workpaper is too large to open.")
  const catalog = indirectCatalog.parse(
    link.metadata.catalog === undefined
      ? await loadCatalog()
      : link.metadata.catalog
  )
  if (catalog.case_id !== caseId)
    throw Error("The saved method belongs to another case.")
  const request = indirectRequest.parse(
    JSON.parse(envelope.scenario_json).inputs
  )
  const review = await verifyIndirectReview(envelope, catalog, request)
  const attached = links.filter(
    (item) => item.source_anchor.workpaper_sha256 === envelope.scenario_sha256
  )
  const sources = review.value.sources.map((item) => item.id).sort()
  if (
    link.source_anchor.workpaper_sha256 !== envelope.scenario_sha256 ||
    attached.some(
      (item) => item.case_id !== caseId || item.target_type !== "evidence"
    ) ||
    JSON.stringify(attached.map((item) => item.target_id).sort()) !==
      JSON.stringify(sources)
  )
    throw Error(
      "The attached files do not match the sources saved in this workpaper."
    )
  return { review, catalog }
}
