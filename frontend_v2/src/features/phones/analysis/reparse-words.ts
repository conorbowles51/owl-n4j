import type { ApproachResult } from "./analysis-api"

/** 05 section 17.3: the report's records against an independent tool's reading, one tab per disagreement kind. */
export const TABS = [
  { kind: "count_differs", label: "Totals differ" },
  { kind: "only_in_reparse", label: "Only the tool read" },
  { kind: "only_in_report", label: "Only in the report" },
  { kind: "time_differs", label: "Times differ" },
  { kind: "value_differs", label: "Content differs" },
  { kind: "present_in_both", label: "Read the same" },
]

const KIND_NAMES: Record<string, [string, string]> = {
  sms: ["text message", "text messages"], call: ["call", "calls"], whatsapp_message: ["WhatsApp message", "WhatsApp messages"],
  contact: ["contact", "contacts"], web_history: ["web history entry", "web history entries"],
}

type Side = { instant?: string | null; original?: string | null; shown?: Record<string, unknown>; artefact?: string; row_index?: number }
type M = Record<string, unknown>
const n = (v: unknown) => Number(v ?? 0).toLocaleString("en-US")
const name = (k: unknown, count = 1) => (KIND_NAMES[String(k)] || [String(k), String(k)])[count === 1 ? 0 : 1]

function shown(s?: Side): string {
  const v = s?.shown || {}
  const parts = ["party", "url", "name", "body", "direction", "duration", "duration_s", "title"]
    .filter((k) => v[k] !== undefined && v[k] !== null && v[k] !== "")
    .map((k) => `${k.replace("_s", "").replace("_", " ")}: ${String(v[k])}`)
  return parts.join("; ") || "(no value)"
}

function when(s?: Side): string {
  if (!s?.instant) return "no time"
  return `${s.instant} (as written: ${s.original ?? "not given"})`
}

export function reparseWords(r: ApproachResult) {
  const m = r.measures as M
  const readBy = String(m.read_by || "read by the tool")
  const rep = m.report as Side | undefined
  const tool = m.reparse as Side | undefined
  const where = tool?.artefact ? ` (${tool.artefact}, row ${tool.row_index})` : ""
  if (r.kind === "count_differs") {
    return { title: `${name(m.compared, 2)}: ${n(m.report_count)} in the report, ${n(m.reparse_count)} ${readBy}`,
      line: "The totals differ. The tabs list each record on one side only, and each pair whose time or content differs." }
  }
  if (r.kind === "only_in_reparse") {
    return { title: `A ${name(m.compared)} ${readBy}${where}, not in the report`,
      line: `${shown(tool)}. Time ${when(tool)}. This could be a record the report did not decode, or a deleted row the tool read.` }
  }
  if (r.kind === "only_in_report") {
    return { title: `A ${name(m.compared)} in the report that the tool did not read`, line: `${shown(rep)}. Time ${when(rep)}.` }
  }
  if (r.kind === "time_differs") {
    return { title: `A ${name(m.compared)} at different times: ${m.difference_hours} hours apart`,
      line: `In the report: ${when(rep)}. ${readBy[0].toUpperCase()}${readBy.slice(1)}${where}: ${when(tool)}.` }
  }
  if (r.kind === "value_differs") {
    return { title: `A ${name(m.compared)} at the same time with different content`,
      line: `In the report: ${shown(rep)}. ${readBy[0].toUpperCase()}${readBy.slice(1)}${where}: ${shown(tool)}.` }
  }
  return { title: `A ${name(m.compared)} the report and the tool read the same`, line: `${shown(rep)}. ${readBy}${where}.` }
}
