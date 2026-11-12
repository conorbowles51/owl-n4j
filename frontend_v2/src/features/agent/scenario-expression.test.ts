import { describe, expect, it } from "vitest"
import { evaluateScenario } from "./scenario-expression"

describe("safe scenario calculations", () => {
  const values = new Map([["amount", 100], ["rate", .2]])
  it("supports assumptions, precedence, parentheses, signed numbers and exponents", () => {
    expect(evaluateScenario("amount * (1 + rate) - 2e1 / +2", values)).toBe(110)
    expect(evaluateScenario("-amount + .5", values)).toBe(-99.5)
  })
  it.each(["window.location", "fetch('https://example.com')", "amount=10", "amount.constructor", "amount[0]", "globalThis", "1 / 0", "1e999", "(amount", "amount rate", ""])("rejects unsafe or invalid expression %s", (expression) => {
    expect(() => evaluateScenario(expression, values)).toThrow()
  })
  it("rejects pathological nesting", () => {
    expect(() => evaluateScenario("(".repeat(70) + "1" + ")".repeat(70), values)).toThrow("deeply nested")
  })
})
