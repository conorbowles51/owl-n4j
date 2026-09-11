import { savedAnalysisSummary } from "./saved-analysis-summary"
import type { CaseworkEntry } from "@/features/workspace/casework-api"
import { transactionDetail } from "./transaction-detail"
import { formatLedgerAmount } from "./ledger-format"

const escape = (value: unknown) =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (char) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        char
      ]!
  )

// A report of this saved entry only. Never silently append wider case records.
export function findingReport(
  entry: CaseworkEntry,
  caseId: string,
  files?: Record<string, string>
) {
  if (entry.case_id !== caseId)
    throw Error("The saved work belongs to another case.")
  const rows = new Map<
    string,
    { row: ReturnType<typeof transactionDetail.parse>; filename: string }
  >()
  for (const link of entry.links) {
    if (link.case_id !== caseId)
      throw Error("A supporting link belongs to another case.")
    const ids = Array.isArray(link.source_anchor.financial_transaction_ids)
      ? link.source_anchor.financial_transaction_ids
      : []
    for (const value of Array.isArray(link.metadata.transactions)
      ? link.metadata.transactions
      : []) {
      const row = transactionDetail.parse(value)
      if (row.case_id !== caseId || !ids.includes(row.key))
        throw Error("A saved payment does not match its supporting link.")
      rows.set(row.key, { row, filename: link.target_label || "Statement" })
    }
  }
  const analysisNotes = entry.links
    .flatMap((link) => {
      const value = link.metadata.analysis
      if (!value || typeof value !== "object" || !("summary" in value))
        return []
      const details =
        "details" in value && value.details && typeof value.details === "object"
          ? (value.details as Record<string, unknown>)
          : {}
      const pairs = Array.isArray(details.pairs) ? details.pairs : []
      return [
        `<h2>Saved analysis</h2><p>${escape(value.summary)}</p>${savedAnalysisSummary(
          value
        )
          .map((line) => `<p>${escape(line)}</p>`)
          .join(
            ""
          )}${details.basis ? `<p class="note">${escape(details.basis)}</p>` : ""}${
          pairs.length
            ? `<ol>${pairs
                .map((pair) => {
                  if (!pair || typeof pair !== "object") return ""
                  const p = pair as Record<string, unknown>
                  const debit = rows.get(String(p.debit_id))?.row,
                    credit = rows.get(String(p.credit_id))?.row
                  return `<li>${escape(debit?.account_label || debit?.account_id || "Outgoing payment")} (${escape(debit?.ref_id)}) to ${escape(credit?.account_label || credit?.account_id || "Incoming payment")} (${escape(credit?.ref_id)})</li>`
                })
                .join("")}</ol>`
            : ""
        }`,
      ]
    })
    .join("")
  const lines = [...rows.values()]
    .map(
      ({ row, filename }) =>
        `<tr><td>${escape(row.ordering_date)}</td><td>${escape(row.description)}</td><td>${escape(row.account_type === "credit_card" ? (row.direction === "credit" ? "Card credit" : "Card charge") : row.direction === "credit" ? "Money in" : row.direction === "debit" ? "Money out" : row.direction)}</td><td>${escape(formatLedgerAmount(row.amount_minor, row.currency).text)} ${escape(row.currency)}</td><td>${escape(filename)}<br>${escape(row.ref_id)}</td></tr>`
    )
    .join("")
  return `<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>${escape(entry.title || "Financial note")}</title><style>body{font:16px/1.55 system-ui,sans-serif;max-width:1000px;margin:40px auto;padding:0 24px;color:#202020}h1{font-size:28px}table{width:100%;border-collapse:collapse;font-size:14px}th,td{padding:10px;border:1px solid #ccc;text-align:left;vertical-align:top}.note{white-space:pre-wrap}.muted{color:#555;font-size:14px}@media print{body{margin:0;padding:0}thead{display:table-header-group}tr{break-inside:avoid}}</style><body>
<h1>${escape(entry.title || "Financial note")}</h1><p class="muted">${escape(entry.entry_type)} · ${escape(entry.author_name || entry.author_email || "Author not recorded")}<br>Saved ${escape(entry.updated_at || entry.created_at || "date not recorded")}<br>Case ${escape(caseId)} · Record ${escape(entry.id)}</p>
<h2>Observation</h2><p class="note">${escape(entry.body)}</p>
${rows.size ? `<h2>Selected payments (${rows.size})</h2><p class="muted">These values were recorded when this selection was saved. Later corrections are available by reopening the linked transactions in Loupe.</p><table><thead><tr><th>Date</th><th>Description</th><th>In or out</th><th>Amount</th><th>Statement and reference</th></tr></thead><tbody>${lines}</tbody></table>` : ""}
${analysisNotes}<h2>Supporting records</h2><ul>${entry.links.map((link) => `<li>${files?.[link.target_id] ? `<a href="${escape(files[link.target_id])}">${escape(link.target_label || link.target_id)}</a>` : escape(link.target_label || link.target_id)}${link.metadata.schema === "loupe.financial.event_context/1" ? `<br>${escape(link.metadata.date)}: ${escape(link.metadata.summary)}` : ""}${Array.isArray(link.source_anchor.financial_ref_ids) ? `<br>${link.source_anchor.financial_ref_ids.map(escape).join(", ")}` : ""}</li>`).join("")}</ul><p class="muted">This report contains this saved note and its attached payment values and references. ${files ? "The supporting original PDFs are included in the statements folder. Whole PDFs may contain other statement periods. Unrelated case records are not included." : "Original statement files and unrelated case records are not included."} Open the saved note in Loupe to inspect its evidence.</p></body></html>`
}
