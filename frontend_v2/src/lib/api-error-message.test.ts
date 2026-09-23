import { expect, it } from "vitest"
import { apiErrorMessage } from "./api-error-message"

it("names invalid form fields without exposing the echoed request payload", () => {
  const message = apiErrorMessage(
    [
      {
        type: "missing",
        loc: ["body", "sections", 1, "period_start"],
        msg: "Field required",
        input: { confidential: "private-source-text" },
      },
    ],
    422
  )
  expect(message).toBe("Sections · 2 · period start: Field required")
  expect(message).not.toContain("private-source-text")
})

it("explains stale revisions and preserves purposeful server messages", () => {
  expect(
    apiErrorMessage(
      [
        {
          loc: ["body", "expected_revision"],
          msg: "String should match pattern",
        },
      ],
      422
    )
  ).toBe(
    "The saved records changed. Reload this view and review the action again."
  )
  expect(
    apiErrorMessage({ message: "This import is still running." }, 409)
  ).toBe("This import is still running.")
  expect(apiErrorMessage("The account could not be saved.", 409)).toBe(
    "The account could not be saved."
  )
})

it("uses a bounded readable fallback for malformed and lengthy validation errors", () => {
  expect(
    apiErrorMessage({ unexpected: "private-source-text" }, 500)
  ).not.toContain("private-source-text")
  const message = apiErrorMessage(
    Array.from({ length: 12 }, (_, n) => ({
      loc: ["body", "rows", n],
      msg: "Field required",
    })),
    422
  )
  expect(message).toContain("Check 7 additional fields.")
  expect(message).not.toContain("Rows · 12")
})
