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

  it("counts a prepared file's work from the review queue, never from its own checks", () => {
    const none = { waiting: 0, unreadable: 0, ready: 0 }
    // The register still says one period has checks (a saved statement's
    // check history), but the queue lists nothing: no phantom work.
    const quiet = statementFileCard(
      processed,
      saved({ periods_with_checks: 1, periods: [{ id: "p" }], current_transactions: 3 }),
      { statusLoaded: true, queue: none }
    )
    expect(quiet.needsAction).toBe(false)
    const work = statementFileCard(
      processed,
      saved({ periods: [{ id: "p" }], current_transactions: 3 }),
      { statusLoaded: true, queue: { ...none, waiting: 1 } }
    )
    expect(work.needsAction).toBe(true)
    const ready = statementFileCard(
      processed,
      saved({ available_periods: 2 }),
      { statusLoaded: true, queue: { ...none, ready: 2 } }
    )
    expect(ready.needsAction).toBe(true)
    // A read file never prepared is still work (it has no queue entry yet).
    const unprepared = statementFileCard(processed, undefined, {
      statusLoaded: true,
      queue: none,
    })
    expect(unprepared.needsAction).toBe(true)
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

describe("copies on the file card", () => {
  const ignored = (filename: string) => ({
    statement_id: null,
    currency: "USD",
    decision: {
      policy: "p",
      reading_revision: "d".repeat(64),
      revision: "e".repeat(64),
      status: "ignored",
      label: "Duplicate - Ignored by system",
      reason: "",
      current: true,
      matched_fields: [],
      retained: {
        evidence_file_id: "00000000-0000-4000-8000-000000000001",
        filename,
        page_number: 1,
      },
    },
  })
  it("names the retained file when every statement is a copy, outside Needs action", () => {
    const card = statementFileCard(
      processed,
      saved({
        prepared_periods: 2,
        ignored_periods: 2,
        duplicate_dispositions: [ignored("Kept.pdf"), ignored("Kept.pdf")],
      }),
      { statusLoaded: true }
    )
    expect(card.label).toBe(
      "All 2 statements are copies of Kept.pdf — nothing to review"
    )
    expect(card.needsAction).toBe(false)
  })
  it("says how many are copies when only some are, and keeps the rest as work", () => {
    const card = statementFileCard(
      processed,
      saved({
        prepared_periods: 3,
        ignored_periods: 1,
        periods_with_checks: 2,
        duplicate_dispositions: [ignored("Kept.pdf")],
      }),
      { statusLoaded: true }
    )
    expect(card.label).toContain("1 of 3 statements are copies of Kept.pdf")
    expect(card.needsAction).toBe(true)
  })
})
