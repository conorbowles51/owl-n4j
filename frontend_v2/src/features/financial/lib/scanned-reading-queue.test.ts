import { expect, it } from "vitest"
import {
  scannedPageProposal,
  scannedPageProposals,
  verifyQueuedMapping,
} from "./scanned-reading-queue"
import {
  scanFixture,
  sourceFixture,
  mappingFixture,
} from "./__fixtures__/scanned-readings"
it("preserves exact original cells, unclassified date roles and explicit undated opt-in", () => {
  const proposal = scannedPageProposal(
    scanFixture,
    scanFixture.pages[0],
    sourceFixture(1),
    false
  )
  expect(proposal.rows).toHaveLength(1)
  expect(proposal.columns).toEqual([
    { column_index: 0, meaning: "date" },
    { column_index: 1, meaning: "amount" },
  ])
  expect(
    scannedPageProposal(
      scanFixture,
      scanFixture.pages[0],
      sourceFixture(1),
      true
    ).rows.map((r) => r.row_index)
  ).toEqual([0, 1])
  expect(
    verifyQueuedMapping(mappingFixture(proposal), proposal).candidates[0].status
  ).toBe("pending")
})
it("refuses stale, cross-case or altered cell proposals before writing", () => {
  for (const patch of [
    { case_id: "other" },
    { page_number: 2 },
    { source_revision: "d".repeat(64) },
  ])
    expect(() =>
      scannedPageProposal(
        scanFixture,
        scanFixture.pages[0],
        { ...sourceFixture(1), ...patch },
        false
      )
    ).toThrow()
  const source = sourceFixture(1)
  source.rows[0].cells[1].expected_text = "100.00"
  expect(() =>
    scannedPageProposal(scanFixture, scanFixture.pages[0], source, false)
  ).toThrow()
})
it("checks the persisted mapping and each exact candidate cell", () => {
  const proposal = scannedPageProposal(
    scanFixture,
    scanFixture.pages[0],
    sourceFixture(1),
    false
  )
  const changed = mappingFixture(proposal)
  changed.candidates[0].original.cells[1].text = "100.00"
  expect(() => verifyQueuedMapping(changed, proposal)).toThrow()
  const missing = mappingFixture(proposal)
  missing.candidates = []
  expect(() => verifyQueuedMapping(missing, proposal)).toThrow()
})
it("does not turn a nominated amount into an unrelated page header meaning", () => {
  const source = sourceFixture(1)
  source.rows.unshift({
    ...source.rows[0],
    row_index: 9,
    cells: [{ ...source.rows[0].cells[1], expected_text: "Account number" }],
  })
  const proposal = scannedPageProposal(
    scanFixture,
    scanFixture.pages[0],
    source,
    false
  )
  expect(proposal.columns.find((c) => c.column_index === 1)?.meaning).toBe(
    "amount"
  )
  expect(proposal.rows.map((r) => r.row_index)).toEqual([0])
})

it("separates shifted amount columns instead of marking descriptions as money", () => {
  const source = sourceFixture(1)
  const locator = source.rows[0].cells[0].locator
  source.columns = [0, 1, 2]
  source.rows = [
    {
      row_index: 9,
      cells: [
        { column_index: 0, expected_text: "Date", locator },
        { column_index: 1, expected_text: "Amount", locator },
      ],
    },
    {
      row_index: 10,
      cells: [
        { column_index: 0, expected_text: "01/02", locator },
        { column_index: 1, expected_text: "SHOP", locator },
        { column_index: 2, expected_text: "14.00", locator },
      ],
    },
    {
      row_index: 11,
      cells: [
        { column_index: 0, expected_text: "02/02", locator },
        { column_index: 1, expected_text: "0.00", locator },
      ],
    },
  ]
  const page = {
    ...scanFixture.pages[0],
    undated_charges: [],
    suggestions: [
      {
        row_index: 10,
        date_source: source.rows[1].cells[0],
        amount_source: source.rows[1].cells[2],
      },
      {
        row_index: 11,
        date_source: source.rows[2].cells[0],
        amount_source: source.rows[2].cells[1],
      },
    ],
  }
  const groups = scannedPageProposals(scanFixture, page, source, false)
  expect(groups.map((g) => g.rows.map((r) => r.row_index))).toEqual([
    [10],
    [11],
  ])
  expect(groups[0].columns.map((c) => c.meaning)).toEqual([
    "date",
    "unknown",
    "amount",
  ])
  expect(groups[1].columns.map((c) => c.meaning)).toEqual([
    "date",
    "amount",
    "unknown",
  ])
  expect(groups[0].rows[0].cells[1].expected_text).toBe("SHOP")
})
