/**
 * What a folder or file holds, for its colour on the Evidence list (lx-style, Neil 2 Nov: mock2 #11). The word is
 * always shown beside the colour. A file the bank-file check calls a bank file is "Statements"; otherwise the kind
 * comes from the folder's or file's own name, and the tag says so on hover. Nothing here changes how a file is
 * processed.
 */
import type { FileRoute } from "../hooks/use-route-checks"

export type EvidenceKind = "Statements" | "Phone" | "Document"

export const EVIDENCE_KIND_TONE: Record<EvidenceKind, { text: string; edge: string; border: string }> = {
  Statements: { text: "text-source-1", edge: "hsl(var(--source-1))", border: "border-source-1" },
  Phone: { text: "text-source-4", edge: "hsl(var(--source-4))", border: "border-source-4" },
  Document: { text: "text-source-3", edge: "hsl(var(--source-3))", border: "border-source-3" },
}

const STATEMENTS = /(^|[^a-z])(bank|statements?|statm|financial)([^a-z]|$)/i
const PHONE = /(messages|phone|device|cellebrite|ufdr|extraction)/i
const DOCUMENT = /\.(pdf|docx?|rtf|odt|txt)$/i

export function evidenceKind(name: string, route?: FileRoute): { kind: EvidenceKind; basis: string } | null {
  if (route?.outcome === "native") return { kind: "Statements", basis: "The bank-file check reads this as a bank file" }
  if (STATEMENTS.test(name)) return { kind: "Statements", basis: "From the name" }
  if (PHONE.test(name)) return { kind: "Phone", basis: "From the name" }
  if (DOCUMENT.test(name)) return { kind: "Document", basis: "From the file type" }
  return null
}
