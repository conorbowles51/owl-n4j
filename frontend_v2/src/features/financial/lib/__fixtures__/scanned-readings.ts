import { resultSchema } from "../pdf-page-scan"
import type { ScannedPageProposal } from "../scanned-reading-queue"
export const scanFixture = resultSchema.parse({
  case_id: "case",
  evidence_file_id: "file",
  start_page: 1,
  end_page: 2,
  table_index: 0,
  date_column: 0,
  amount_column: 1,
  currency: "GBP",
  applied: false,
  limitation: "Synthetic proposals",
  suggested_rows: 2,
  undated_charge_rows: 2,
  pages: [1, 2].map((page_number) => ({
    page_number,
    checked: true,
    reason: null,
    checked_rows: 2,
    source_revision: (page_number === 1 ? "a" : "b").repeat(64),
    suggestions: [
      {
        row_index: 0,
        date_source: { column_index: 0, expected_text: "01/02/2026" },
        amount_source: { column_index: 1, expected_text: "10.00" },
      },
    ],
    undated_charges: [
      {
        row_index: 1,
        label_source: { column_index: 0, expected_text: "Fee" },
        amount_sources: [{ column_index: 1, expected_text: "0.00" }],
        date_unknown: true,
        reason: "Synthetic undated charge",
      },
    ],
  })),
})
export function sourceFixture(page: number) {
  return {
    case_id: "case",
    evidence_file_id: "file",
    page_number: page,
    table_index: 0,
    table_count: 1,
    source_revision: (page === 1 ? "a" : "b").repeat(64),
    table_source: "text_alignment",
    geometry_source: "cell_rectangles",
    locator: {},
    columns: [0, 1],
    rows: [
      {
        row_index: 0,
        cells: [
          { column_index: 0, expected_text: "01/02/2026", locator: {} },
          { column_index: 1, expected_text: "10.00", locator: {} },
        ],
      },
      {
        row_index: 1,
        cells: [
          { column_index: 0, expected_text: "Fee", locator: {} },
          { column_index: 1, expected_text: "0.00", locator: {} },
        ],
      },
    ],
    applied: false,
  }
}
export function mappingFixture(proposal: ScannedPageProposal) {
  return {
    id: `mapping-${proposal.page_number}`,
    case_id: proposal.case_id,
    evidence_file_id: proposal.evidence_file_id,
    mapping_revision: "c".repeat(64),
    applied: false,
    original: { proposal: { ...proposal, context: {} } },
    candidates: proposal.rows.map((row) => ({
      id: `candidate-${proposal.page_number}-${row.row_index}`,
      row_index: row.row_index,
      status: "pending",
      original: {
        cells: row.cells.map((cell) => ({
          column_index: cell.column_index,
          text: cell.expected_text,
          proposed_meaning: proposal.columns.find(
            (c) => c.column_index === cell.column_index
          )!.meaning,
        })),
      },
    })),
  }
}
