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
