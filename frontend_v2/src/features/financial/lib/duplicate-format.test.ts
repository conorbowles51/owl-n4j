import { expect, it } from "vitest"
import { duplicateCandidates } from "@/test/duplicate-fixture"
import {
  duplicateMatchLabel,
  readDuplicateCandidates,
} from "./duplicate-format"

it("accepts a complete comparison and preserves actual status separately from match", () => {
  const data = readDuplicateCandidates(duplicateCandidates(), "case-1")
  expect(data.groups[0].members[1].status).toBe("superseded")
  expect(data.groups[0].members[1].match).toBe("identical_reading")
})
it.each([
  (d: ReturnType<typeof duplicateCandidates>) => {
    d.case_id = "other"
  },
  (d: ReturnType<typeof duplicateCandidates>) => {
    d.compared = 3
  },
  (d: ReturnType<typeof duplicateCandidates>) => {
    d.groups[0].members[1].document_id = "first"
  },
  (d: ReturnType<typeof duplicateCandidates>) => {
    d.groups[0].members[1].rows_by_status.admitted = -1
  },
  (d: ReturnType<typeof duplicateCandidates>) => {
    d.groups[0].members[1].match = "comparison_document"
  },
])(
  "rejects wrong cases, inconsistent coverage and malformed group data",
  (change) => {
    const data = duplicateCandidates()
    change(data)
    expect(() => readDuplicateCandidates(data, "case-1")).toThrow()
  }
)
it("labels new match vocabulary without assuming equivalence", () => {
  expect(duplicateMatchLabel("future")).toBe("Unrecognised match (future)")
})

it("retains separate source-hash matches across coverage without inventing reading matches", () => {
  const source = duplicateCandidates()
  const member = source.groups[0].members[0]
  const data = readDuplicateCandidates(
    {
      ...source,
      source_hash_groups: [
        {
          sha256_at_ingestion: "a".repeat(64),
          limitation: "Recorded hashes only",
          members: [member, { ...member, document_id: "separate-coverage" }],
        },
      ],
    },
    "case-1"
  )
  expect(data.source_hash_groups[0].members).toHaveLength(2)
  expect(data.groups).toHaveLength(1)
  expect(() =>
    readDuplicateCandidates(
      {
        ...source,
        source_hash_groups: [
          {
            sha256_at_ingestion: "a".repeat(64),
            limitation: "Recorded hashes only",
            members: [member, member],
          },
        ],
      },
      "case-1"
    )
  ).toThrow()
})

it("accepts a held-file hash sighting without an exclusion revision", () => {
  const source = duplicateCandidates()
  const data = readDuplicateCandidates(
    {
      ...source,
      source_hash_groups: [
        {
          sha256_at_ingestion: "b".repeat(64),
          limitation: "Held readings were not compared",
          members: [source.groups[0].members[0], source.skipped[0]],
        },
      ],
    },
    "case-1"
  )
  expect(data.source_hash_groups[0].members[1].document_id).toBe(
    source.skipped[0].document_id
  )
})
