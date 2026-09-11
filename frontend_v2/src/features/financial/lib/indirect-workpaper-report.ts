import type { CaseworkEntry } from "@/features/workspace/casework-api"
import type { readSavedIndirect } from "./saved-indirect"
import { correctionMoney } from "./correction-contract"

const escape = (value: unknown) =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (char) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        char
      ]!
  )

// Accept only the already-checked record used by the saved-workpaper viewer.
export function indirectWorkpaperReport(
  saved: Awaited<ReturnType<typeof readSavedIndirect>>,
  entry: CaseworkEntry
) {
  const { review, catalog } = saved
  const { value, envelope } = review
  if (entry.case_id !== envelope.case_id)
    throw Error("The workpaper belongs to another case.")
  const source = (field: {
    basis: string
    source_file_id: string | null
    source_location: string
  }) => {
    const file = value.sources.find((item) => item.id === field.source_file_id)
    return `<p>${escape(field.basis || "Explanation not recorded.")}</p><p>${escape(file?.filename || "Supporting file not recorded.")}<br>${escape(field.source_location || "Location not recorded.")}</p>`
  }
  const result =
    value.difference_minor === null
      ? "No result: required amounts or checks are incomplete."
      : `Calculated difference: ${correctionMoney(value.difference_minor, value.inputs.currency)}`
  return `<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>${escape(entry.title || "Saved workpaper")}</title><style>body{font:16px/1.5 system-ui,sans-serif;max-width:1000px;margin:40px auto;padding:0 24px;color:#202020}table{width:100%;border-collapse:collapse}td,th{padding:10px;border:1px solid #ccc;text-align:left;vertical-align:top}td p{margin:0 0 8px}p{white-space:pre-wrap}.reference{overflow-wrap:anywhere;font-size:13px;color:#555}@media print{body{margin:0;padding:0;font-size:11pt}thead{display:table-header-group}tr{break-inside:avoid}}</style><body>
<h1>${escape(value.method_label)}: ${escape(value.inputs.subject)}</h1>
<p>${escape(value.inputs.start_date)} to ${escape(value.inputs.end_date)} · ${escape(value.inputs.currency)}</p>
<h2>${escape(result)}</h2><p>This report uses the inputs and checks saved with this workpaper. Later changes to transactions have not been applied.</p>
${value.missing.length ? `<h2>Still to complete</h2><ul>${value.missing.map((item) => `<li>${escape(item.label)}</li>`).join("")}</ul>` : ""}
<h2>Amounts used in the calculation</h2><table><thead><tr><th>Item</th><th>Amount</th><th>Explanation and source</th></tr></thead><tbody>${value.lines.map((line) => `<tr><th>${line.sign === 1 ? "Add" : "Subtract"}: ${escape(line.label)}</th><td>${escape(line.amount_minor === null ? "Not entered" : correctionMoney(line.amount_minor, value.inputs.currency))}</td><td>${source(line)}</td></tr>`).join("")}</tbody></table>
<h2>Recorded checks</h2>${catalog.requirements
    .map((check) => {
      const field = value.inputs.requirements[check.id]
      return `<h3>${escape(check.label)}: ${field?.status === "reviewed" ? "Marked reviewed" : "Still to review"}</h3>${field ? source(field) : "<p>No review recorded.</p>"}`
    })
    .join("")}
<h2>Calculation notes</h2><p>${escape(value.limitation)}</p>
<h2>Supporting files</h2><ul>${value.sources.map((file) => `<li>${escape(file.filename)}<p class="reference">File ${escape(file.id)}<br>Recorded SHA-256: ${escape(file.sha256 || "Not recorded")}</p></li>`).join("")}</ul><p>The original files are not included in this report. Open the saved workpaper in Loupe to inspect them.</p>
<h2>Saved note</h2><p>${escape(entry.body)}</p>
<p class="reference">${escape(entry.author_name || entry.author_email || "Author not recorded")}<br>Saved ${escape(entry.updated_at || entry.created_at || "date not recorded")}<br>Case ${escape(entry.case_id)}<br>Note ${escape(entry.id)}<br>Workpaper SHA-256: ${escape(envelope.scenario_sha256)}<br>Method reference: ${escape(value.reference)}, section ${escape(value.reference_section)}</p></body></html>`
}
