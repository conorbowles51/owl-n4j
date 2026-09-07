/**
 * Reading an ingestion run for display.
 *
 * The tests that matter here are about what this module refuses to conclude.
 *
 * `needsAttention` is the one signal that will put a run in front of a reader
 * who did not ask for it, so what it is true of is a decision, not a detail. It
 * is true of every ending that left the ledger holding less than the evidence
 * handed to it, and false for a status this build does not recognise, because
 * raising an alarm about a word we cannot read would be inventing a problem.
 *
 * The rest guard against rendering a gap as a fact: a missing timestamp as an
 * empty cell, a deleted account as nobody, an unfinished run as a duration of
 * zero.
 */

import { describe, expect, it } from "vitest"

import type { IngestionRun } from "../api"
import {
  RUN_COUNTS_ARE_HISTORY,
  isProvisionalAccountRun,
  readRunOperationStatus,
  formatRunTime,
  readRunStarter,
  readRunStatus,
  runDuration,
} from "./run-format"

function run(overrides: Partial<IngestionRun> = {}): IngestionRun {
  return {
    key: "run-1",
    case_id: "case-1",
    status: "completed",
    code_version: null,
    ruleset_version: null,
    config: {},
    started_by_user_id: null,
    started_by_email: null,
    started_at: null,
    completed_at: null,
    documents_seen: 0,
    transactions_admitted: 0,
    transactions_quarantined: 0,
    error: null,
    notes: null,
    ...overrides,
  }
}

describe("readRunStatus", () => {
  it("names every status the backend can store", () => {
    for (const status of [
      "pending",
      "running",
      "completed",
      "failed",
      "aborted",
    ]) {
      const reading = readRunStatus(status)
      expect(reading.value).toBe(status)
      expect(reading.label).not.toBe("")
      expect(reading.label).not.toMatch(/unrecognised/i)
      expect(reading.description).not.toBe("")
    }
  })

  it("draws attention to every ending that left the ledger short", () => {
    // Failed and aborted stopped part way. Pending and running have not
    // finished, so what is in the ledger from them is not what was handed in.
    expect(readRunStatus("failed").needsAttention).toBe(true)
    expect(readRunStatus("aborted").needsAttention).toBe(true)
    expect(readRunStatus("pending").needsAttention).toBe(true)
    expect(readRunStatus("running").needsAttention).toBe(true)
  })

  it("says nothing about a run that finished", () => {
    expect(readRunStatus("completed").needsAttention).toBe(false)
  })

  it("tells apart a run that broke from one that was stopped", () => {
    // The backend keeps these separate on purpose. Collapsing them here would
    // hide, from anyone later asking why a ledger is incomplete, whether a
    // person decided that or a fault caused it.
    const failed = readRunStatus("failed")
    const aborted = readRunStatus("aborted")
    expect(failed.label).not.toBe(aborted.label)
    expect(failed.description).not.toBe(aborted.description)
  })

  it("gives each status its own badge rather than falling through to the loud one", () => {
    const variants = [
      "pending",
      "running",
      "completed",
      "failed",
      "aborted",
    ].map((s) => readRunStatus(s).variant)
    expect(variants).not.toContain("default")
    expect(new Set(variants).size).toBe(variants.length)
  })

  it("marks a status this build has never heard of, and does not blank it", () => {
    const reading = readRunStatus("reaped")
    expect(reading.value).toBeNull()
    expect(reading.raw).toBe("reaped")
    expect(reading.label).toContain("reaped")
    expect(reading.description).toContain("reaped")
  })

  it("does not raise an alarm about a status it cannot read", () => {
    // The unknown word may well name a perfectly ordinary ending. Treating it
    // as trouble would report a problem this build has no grounds to claim.
    expect(readRunStatus("reaped").needsAttention).toBe(false)
    expect(readRunStatus("reaped").variant).not.toBe("default")
  })
})

describe("readRunStarter", () => {
  it("prefers the email, which survives the account being deleted", () => {
    expect(
      readRunStarter(
        run({ started_by_email: "alex@owl.test", started_by_user_id: "u-1" })
      )
    ).toBe("alex@owl.test")
  })

  it("falls back to the id when only that is left", () => {
    expect(readRunStarter(run({ started_by_user_id: "u-1" }))).toContain("u-1")
  })

  it("says the starter was not recorded rather than rendering nobody", () => {
    expect(readRunStarter(run())).toBe("Not recorded")
  })
})

describe("formatRunTime", () => {
  it("reads a stored timestamp the same way on every machine", () => {
    // Fixed locale, not the browser's, so two people reading the same case see
    // the same run.
    const text = formatRunTime("2024-03-04T09:07:00Z")
    expect(text).toMatch(/2024/)
    expect(text).toMatch(/Mar/)
  })

  it("states an absent time rather than leaving a gap", () => {
    expect(formatRunTime(null)).toBe("Not recorded")
    expect(formatRunTime("")).toBe("Not recorded")
  })

  it("shows a value it cannot parse as it arrived", () => {
    // "Invalid Date" is this screen's word, not the record's. Showing the
    // stored value keeps the fault attributable.
    expect(formatRunTime("not a date")).toBe("not a date")
  })
})

describe("runDuration", () => {
  it("measures a run that has both ends", () => {
    expect(
      runDuration(
        run({
          started_at: "2024-03-04T09:00:00Z",
          completed_at: "2024-03-04T09:00:42Z",
        })
      )
    ).toBe("42s")
    expect(
      runDuration(
        run({
          started_at: "2024-03-04T09:00:00Z",
          completed_at: "2024-03-04T09:05:30Z",
        })
      )
    ).toBe("5m 30s")
    expect(
      runDuration(
        run({
          started_at: "2024-03-04T09:00:00Z",
          completed_at: "2024-03-04T11:20:00Z",
        })
      )
    ).toBe("2h 20m")
  })

  it("gives no duration for a run that has not ended", () => {
    // Rather than zero, which would read as a run that did nothing instantly.
    expect(runDuration(run({ started_at: "2024-03-04T09:00:00Z" }))).toBeNull()
  })

  it("gives no duration when the two timestamps disagree", () => {
    expect(
      runDuration(
        run({
          started_at: "2024-03-04T09:05:00Z",
          completed_at: "2024-03-04T09:00:00Z",
        })
      )
    ).toBeNull()
  })

  it("gives no duration for a time it cannot parse", () => {
    expect(
      runDuration(
        run({ started_at: "whenever", completed_at: "2024-03-04T09:00:00Z" })
      )
    ).toBeNull()
  })
})

describe("RUN_COUNTS_ARE_HISTORY", () => {
  it("says the counts are the attempt's record and not a count of the ledger", () => {
    // Held as one string so the screen and this test cannot drift.
    expect(RUN_COUNTS_ARE_HISTORY).toMatch(/recorded/)
    expect(RUN_COUNTS_ARE_HISTORY).toMatch(
      /not a count of what is in the ledger now/
    )
  })
})

it("describes account setup without claiming imported money", () => {
  const setup = run({
    config: { operation: "provisional_candidate_account" },
    status: "failed",
  })
  expect(isProvisionalAccountRun(setup)).toBe(true)
  expect(readRunOperationStatus(setup).needsAttention).toBe(true)
  expect(readRunOperationStatus(setup).description).toContain(
    "does not import transactions"
  )
  expect(
    readRunOperationStatus({ ...setup, status: "completed" }).description
  ).toContain("no transactions were imported")
})
it("does not suppress import warnings when counters contradict the operation label", () => {
  const setup = run({
    config: { operation: "provisional_candidate_account" },
    status: "failed",
    transactions_admitted: 1,
  })
  expect(isProvisionalAccountRun(setup)).toBe(false)
  expect(readRunOperationStatus(setup)).toEqual(readRunStatus("failed"))
})
it("does not guess the meaning of a future account setup status", () => {
  expect(
    readRunOperationStatus(
      run({
        config: { operation: "provisional_candidate_account" },
        status: "future",
      })
    )
  ).toEqual(readRunStatus("future"))
})
