import type { Profile } from "../schemas"
import { labelText } from "./labels"

const fmt = (n: number) => n.toLocaleString("en-US")

/** Copy profile as text (03 section 7.3): the summary's facts as plain lines. */
export function profileText(p: Profile): string {
  const lines = [`${p.phone.label} Phone summary`, p.verdict.sentence, `Owner: ${p.owner.label ? labelText(p.owner.label) : "not found"} (${p.owner.words})`]
  lines.push(`Report: ${p.report.filename ?? "not recorded"}, ${p.report.form ?? "form not recorded"}, version ${p.report.report_version ?? "not recorded"}`)
  if (p.report.container_sha256) lines.push(`SHA-256 of what was received: ${p.report.container_sha256}`)
  for (const s of p.selection) lines.push(`${s.name}: ${s.verbatim}${s.meaning ? `. ${s.meaning}` : ""}`)
  lines.push(`Files: ${fmt(p.files.total)}`)
  for (const [k, v] of Object.entries(p.files.verification)) lines.push(`  ${k}: ${fmt(v)}`)
  for (const d of p.data_periods) lines.push(`${d.signal}: ${fmt(d.records)}${d.first_words ? `, ${d.first_words} to ${d.last_words}` : ""}`)
  return lines.join("\n")
}
