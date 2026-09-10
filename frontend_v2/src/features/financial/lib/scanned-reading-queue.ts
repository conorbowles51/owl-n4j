import { z } from "zod"
import { sourceTable } from "./pdf-source-table"
import type { PdfPageScan } from "./pdf-page-scan"
import { proposePdfHeaders } from "./pdf-header-proposals"
import { candidateMapping } from "./candidate-contract"
export function scannedPageProposal(
  scan: PdfPageScan,
  page: PdfPageScan["pages"][number],
  raw: unknown,
  includeUndated: boolean
) {
  const source = sourceTable.parse(raw)
  if (
    source.case_id !== scan.case_id ||
    source.evidence_file_id !== scan.evidence_file_id ||
    source.page_number !== page.page_number ||
    source.table_index !== scan.table_index ||
    source.source_revision !== page.source_revision
  )
    throw Error("A scanned source changed. Scan again before adding readings.")
  const chosen = new Map<
    number,
    { column_index: number; expected_text: string }[]
  >()
  for (const row of page.suggestions)
    chosen.set(row.row_index, [
      ...(chosen.get(row.row_index) ?? []),
      row.date_source,
      row.amount_source,
    ])
  if (includeUndated)
    for (const row of page.undated_charges)
      chosen.set(row.row_index, [
        ...(chosen.get(row.row_index) ?? []),
        row.label_source,
        ...row.amount_sources,
      ])
  if (!chosen.size) throw Error("No selected proposals on this page.")
  const byRow = new Map(source.rows.map((r) => [r.row_index, r]))
  if (
    byRow.size !== source.rows.length ||
    new Set(source.columns).size !== source.columns.length
  )
    throw Error("Stored source positions are repeated.")
  for (const [index, cells] of chosen) {
    const row = byRow.get(index)
    if (
      !row ||
      cells.some(
        (c) =>
          row.cells.filter(
            (v) =>
              v.column_index === c.column_index &&
              v.expected_text === c.expected_text
          ).length !== 1
      )
    )
      throw Error("A proposed cell differs from its original scan.")
  }
  const amounts = new Set([
    ...page.suggestions.map((r) => r.amount_source.column_index),
    ...(includeUndated
      ? page.undated_charges.flatMap((r) =>
          r.amount_sources.map((c) => c.column_index)
        )
      : []),
  ])
  if (page.suggestions.some((r) => amounts.has(r.date_source.column_index)))
    throw Error("Conflicting date and amount columns need manual page review.")
  const dates = new Set(page.suggestions.map((r) => r.date_source.column_index))
  const headers = proposePdfHeaders(source.rows).proposals
  return {
    schema_version: "pdf-grid-mapping-v1",
    case_id: scan.case_id,
    evidence_file_id: scan.evidence_file_id,
    page_number: page.page_number,
    table_index: scan.table_index,
    source_revision: source.source_revision,
    columns: [...source.columns]
      .sort((a, b) => a - b)
      .map((column_index) => {
        const meanings = [
          ...new Set(
            headers
              .filter((h) => h.column === column_index)
              .map((h) => h.meaning)
          ),
        ]
        return {
          column_index,
          meaning: amounts.has(column_index)
            ? meanings.length === 1 &&
              ["amount", "debit", "credit"].includes(meanings[0])
              ? meanings[0]
              : "amount"
            : dates.has(column_index)
              ? meanings.length === 1 &&
                [
                  "date",
                  "booking_date",
                  "value_date",
                  "transaction_date",
                ].includes(meanings[0])
                ? meanings[0]
                : "date"
              : meanings.length === 1
                ? meanings[0]
                : "unknown",
        }
      }),
    rows: [...chosen.keys()]
      .sort((a, b) => a - b)
      .map((row_index) => ({
        row_index,
        cells: byRow
          .get(row_index)!
          .cells.map(({ column_index, expected_text }) => ({
            column_index,
            expected_text,
          }))
          .sort((a, b) => a.column_index - b.column_index),
      })),
  }
}
export type ScannedPageProposal = ReturnType<typeof scannedPageProposal>
function canonical(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`
  if (value && typeof value === "object")
    return `{${Object.entries(value)
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([k, v]) => `${JSON.stringify(k)}:${canonical(v)}`)
      .join(",")}}`
  return JSON.stringify(value)
}
export function verifyQueuedMapping(
  raw: unknown,
  proposal: ScannedPageProposal
) {
  const data = candidateMapping.parse(raw)
  const echoed = z
    .object({
      original: z.object({ proposal: z.record(z.string(), z.unknown()) }),
    })
    .parse(raw).original.proposal
  if (
    data.case_id !== proposal.case_id ||
    data.evidence_file_id !== proposal.evidence_file_id ||
    data.candidates.length !== proposal.rows.length ||
    Object.entries(proposal).some(
      ([key, value]) => canonical(echoed[key]) !== canonical(value)
    )
  )
    throw Error(
      "Saved mapping differs from the selected source proposals. Check saved PDF readings before retrying."
    )
  if (
    new Set(data.candidates.map((c) => c.row_index)).size !==
      proposal.rows.length ||
    data.candidates.some(
      (c) => !proposal.rows.some((r) => r.row_index === c.row_index)
    )
  )
    throw Error("Saved candidate rows differ from the queue.")
  const meanings = new Map(
    proposal.columns.map((c) => [c.column_index, c.meaning])
  )
  if (
    new Set(data.candidates.map((c) => c.id)).size !== data.candidates.length ||
    data.candidates.some((candidate) => {
      const row = proposal.rows.find(
        (r) => r.row_index === candidate.row_index
      )!
      return (
        candidate.original.cells.length !== row.cells.length ||
        candidate.original.cells.some(
          (cell, i) =>
            cell.column_index !== row.cells[i].column_index ||
            cell.text !== row.cells[i].expected_text ||
            cell.proposed_meaning !== meanings.get(cell.column_index)
        )
      )
    })
  )
    throw Error(
      "Saved candidate source text or proposed roles differ. Check saved PDF readings before retrying."
    )
  return data
}
