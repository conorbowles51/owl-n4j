import { expect, it } from "vitest"
import { strengthHelp, strengthLabel } from "./judgements"

it("a holder kept as printed says the page prints the name and the holder is not established", () => {
  const help = strengthHelp({ strength: "inferred", origin: "processor", rule_id: "holder.printed_on_statement" })
  expect(help).toContain("The page prints this name.")
  expect(help).toContain("has not been established")
  expect(help).not.toContain("does not print")
})

it("another inferred call keeps its sentence", () => {
  expect(strengthHelp({ strength: "inferred", origin: "processor", rule_id: "category.model" }))
    .toBe("The page does not print this value; the processor worked it out.")
})

it("a holder kept as printed by Claude keeps the holder sentence", () => {
  const help = strengthHelp({ strength: "inferred", origin: "agent", rule_id: "holder.printed_on_statement" })
  expect(help).toContain("The page prints this name.")
  expect(help).not.toContain("Entered by hand")
})

it("a holder call made by Claude is not labelled a hand entry, and says no person confirmed it", () => {
  const label = strengthLabel({ strength: "inferred", origin: "agent", rule_id: "holder.printed_on_statement" })
  expect(label).toBe("Kept as printed by Claude · not confirmed")
  expect(strengthLabel({ strength: "inferred", origin: "agent", rule_id: "agent.page_entry" })).toBe("Hand entry by Claude")
})

it("a statement whose details Claude changed is labelled a change, not a hand entry, and says it is not confirmed", () => {
  const call = { strength: "inferred" as const, origin: "agent", rule_id: "model.statement_account" }
  expect(strengthLabel(call)).toBe("Changed by Claude · not confirmed")
  expect(strengthHelp(call)).toMatch(/until a person confirms or corrects them/)
  expect(strengthHelp(call)).not.toMatch(/Entered by hand/)
})

it("reads a rejected proposal and a person's assumption (the page must not fail on either)", async () => {
  const { judgementSchema, citationHref } = await import("./judgements")
  const base = {
    id: "j", case_id: "c", subject_type: "calculation", subject_id: "k", source_document_id: null,
    statement_period_id: null, evidence_file_id: null, filename: null, rule_id: "assumption.proceeds",
    rule_label: "Assumption", rule_source: "agent-proposals E", target_key: "messages", origin: "person",
    strength: "inferred", summary: "1,000 messages", page: null, category: "assumption",
    category_label: "Assumption", priority: 1, priority_label: "Check first", priority_reason: null,
    status: "confirmed", resolved_by: "Neil", resolved_at: null, resolution_reason: null, adjudication_id: null,
  }
  expect(judgementSchema.parse(base).origin).toBe("person")
  const rejected = judgementSchema.parse({ ...base, origin: "agent", rule_id: "proposal.category", status: "rejected",
    proposal: { kind: "category", citations: ["txn://t"], model: "m" } })
  expect(rejected.status).toBe("rejected")
  expect(rejected.proposal?.citations).toEqual(["txn://t"])
  expect(citationHref("c", "doc://f/3")).toBe("/cases/c/evidence?file=f&page=3")
  expect(citationHref("c", "rec://r#body")).toBe("/cases/c/records/r#body")
})
