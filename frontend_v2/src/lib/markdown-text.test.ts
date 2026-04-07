import { describe, expect, it } from "vitest"
import { markdownToPlainText } from "./markdown-text"

describe("markdownToPlainText", () => {
  it("removes common markdown formatting while keeping readable content", () => {
    const markdown = [
      "## Transaction Details",
      "**BASE_DATA_INVOICE_125000_EUR**",
      "",
      "- Amount: **EUR125,000**",
      '- Source: [04_email_evidence.pdf](evidence://04_email_evidence.pdf)',
    ].join("\n")

    expect(markdownToPlainText(markdown)).toBe(
      "Transaction Details BASE_DATA_INVOICE_125000_EUR Amount: EUR125,000 Source: 04_email_evidence.pdf"
    )
  })

  it("preserves code text and collapses whitespace for compact previews", () => {
    const markdown = [
      "> Use `wire` as the payment method.",
      "",
      "```text",
      "Keep the description vague.",
      "```",
    ].join("\n")

    expect(markdownToPlainText(markdown)).toBe(
      "Use wire as the payment method. Keep the description vague."
    )
  })
})
