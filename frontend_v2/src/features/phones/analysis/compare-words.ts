import { instantWords } from "@/features/phones/lib/time-words"
import type { ApproachResult } from "./analysis-api"

export const TABS = [
  { kind: "identity_check", label: "One device?" },
  { kind: "only_in_earlier", label: "Gone from the later" },
  { kind: "state_changed", label: "Deleted between them" },
  { kind: "only_in_later", label: "New in the later" },
  { kind: "field_changed", label: "Changed" },
  { kind: "type_summary", label: "By type" },
]

const VERDICT: Record<string, string> = {
  same_device_established: "one device: a device identifier is equal in both",
  same_device_indicated: "probably one device: the same owner numbers and mostly the same apps",
  different_device: "different devices: a device identifier present in both differs",
  undetermined: "cannot say from what the reports hold",
}
const REASON: Record<string, string> = {
  created_after_first: "created after the first extraction",
  not_selected_in_other: "the other extraction did not select this type",
  decoder_differs: "the other report's decoder version holds none of this type",
  unexplained: "not accounted for by either extraction",
}
type M = Record<string, unknown>
const n = (v: unknown) => Number(v ?? 0).toLocaleString("en-US")

export function compareWords(r: ApproachResult) {
  const m = r.measures as M
  const pair = ((m.phones as string[]) || []).join(" (earlier) and ") + " (later)"
  const when = m.instant ? instantWords(String(m.instant), "UTC") : undefined
  if (r.kind === "identity_check") {
    const eq = (m.equal as string[]) || []
    const diff = (m.different as string[]) || []
    return { title: `${pair}: ${VERDICT[r.strength] || r.strength}`,
      line: [eq.length ? `Equal in both: ${eq.join(", ")}.` : "", diff.length ? `Different: ${diff.join(", ")}.` : "",
        m.app_jaccard != null ? `Installed apps ${Math.round(Number(m.app_jaccard) * 100)} percent the same.` : ""].filter(Boolean).join(" ") || "No device identifier is present in both reports." }
  }
  if (r.kind === "type_summary") {
    return { title: `${String(m.record_type)}: ${n(m.present_in_both)} in both`,
      line: `Only in the earlier ${n(m.only_in_earlier)}, only in the later ${n(m.only_in_later)}, deleted between them ${n(m.state_changed)}, changed ${n(m.field_changed)}.` }
  }
  if (r.kind === "state_changed") return { title: `${String(m.record_type)}: ${String(m.earlier_state || "Intact")} in the earlier, ${String(m.later_state || "Intact")} in the later`, line: pair, when }
  if (r.kind === "field_changed") return { title: `${String(m.record_type)}: status ${String(m.earlier_status || "not recorded")}, then ${String(m.later_status || "not recorded")}`, line: pair, when }
  const where = r.kind === "only_in_earlier" ? "Only in the earlier extraction" : "Only in the later extraction"
  return { title: `${String(m.record_type)}: ${where.toLowerCase()}`, line: `${where}: ${REASON[String(m.reason)] || String(m.reason)}. ${pair}.`, when }
}
