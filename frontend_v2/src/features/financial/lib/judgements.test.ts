import { expect, it } from "vitest"
import { strengthHelp } from "./judgements"

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
