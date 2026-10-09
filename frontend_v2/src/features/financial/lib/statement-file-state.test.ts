import { describe, expect, it } from "vitest"
import { statementFileCard } from "./statement-file-state"
import { statusPollInterval } from "../hooks/use-statement-register"

const saved = (overrides: Record<string, unknown> = {}) =>
  ({
    evidence_file_id: "f",
    same_pdf_saved_file_ids: [],
    current_transactions: 0,
    incomplete_count: 0,
    awaiting_reconciliation_count: 0,
    incomplete_sources: [],
    receipt_review_count: 0,
    wire_review_count: 0,
    periods: [],
    history_periods: 0,
    prepared_periods: 1,
    ignored_periods: 0,
    duplicate_dispositions: [],
    available_periods: 0,
    ready_periods: [],
    pending_periods: 0,
    periods_with_checks: 0,
    overlapping_periods: 0,
    repeat_periods: 0,
    empty_reading: null,
    ...overrides,
  }) as never
const processed = { id: "f", status: "processed" }

describe("statement file card", () => {
  it("says plainly why an empty reading found nothing and counts it as not imported", () => {
    const card = statementFileCard(
      processed,
      saved({
        empty_reading: {
          reason: "scanned_image",
          message: "Nothing could be read: scanned image, needs visual reading",
        },
      }),
      { statusLoaded: true }
    )
    expect(card.label).toBe(
      "Not imported · Nothing could be read: scanned image, needs visual reading"
    )
    expect(card.notImported).toBe(true)
    expect(card.needsAction).toBe(true)
  })

  it("labels a read file with nothing saved as not imported", () => {
    const card = statementFileCard(processed, undefined, { statusLoaded: true })
    expect(card.label).toBe(
      "Not imported · PDF read · open review to check and import"
    )
    expect(card.notImported).toBe(true)
  })

  it("does not call a file not imported while its status is unknown", () => {
    const card = statementFileCard(processed, undefined, { statusLoaded: false })
    expect(card.label).toBe("Ready to open")
    expect(card.notImported).toBe(false)
  })

  it("keeps saved, duplicate and removed files out of Needs action", () => {
    const imported = statementFileCard(
      processed,
      saved({
        current_transactions: 4,
        periods: [
          {
            id: "p",
            account_id: "a",
            account_label: "A",
            start: null,
            end: null,
            source_status: "admitted",
          },
        ],
      }),
      { statusLoaded: true }
    )
    expect(imported.needsAction).toBe(false)
    expect(imported.notImported).toBe(false)
    const duplicate = statementFileCard(
      processed,
      saved({ ignored_periods: 1 }),
      { statusLoaded: true }
    )
    expect(duplicate.needsAction).toBe(false)
    const removed = statementFileCard(processed, undefined, {
      statusLoaded: true,
      removed: true,
    })
    expect(removed.needsAction).toBe(false)
  })

  it("puts failed readings and files with records or checks under Needs action", () => {
    expect(
      statementFileCard({ id: "f", status: "failed" }, undefined, {
        statusLoaded: true,
      }).needsAction
    ).toBe(true)
    const records = statementFileCard(
      processed,
      saved({ current_transactions: 3, incomplete_count: 2 }),
      { statusLoaded: true }
    )
    expect(records.needsAction).toBe(true)
    expect(records.notImported).toBe(false)
  })
})

describe("status polling", () => {
  it("polls slowly when nothing is reading or importing and stops when hidden", () => {
    const idle = { active: true, uploading: false, importing: false, reading: false }
    expect(statusPollInterval(idle)).toBe(30000)
    expect(statusPollInterval({ ...idle, importing: true })).toBe(5000)
    expect(statusPollInterval({ ...idle, reading: true })).toBe(5000)
    expect(statusPollInterval({ ...idle, uploading: true })).toBe(5000)
    expect(statusPollInterval({ ...idle, active: false })).toBe(false)
  })
})
