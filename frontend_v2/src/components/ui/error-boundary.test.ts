import { describe, expect, it } from "vitest"
import { isDynamicImportError } from "./error-boundary"

describe("isDynamicImportError", () => {
  it.each([
    "Failed to fetch dynamically imported module: /src/features/timeline/components/TimelinePage.tsx",
    "error loading dynamically imported module",
    "Importing a module script failed",
    "Unable to preload CSS for /assets/timeline.css",
  ])("recognizes recoverable module load errors: %s", (message) => {
    expect(isDynamicImportError(new Error(message))).toBe(true)
  })

  it("does not reload for ordinary render errors", () => {
    expect(isDynamicImportError(new Error("Cannot read properties of undefined"))).toBe(false)
    expect(isDynamicImportError(null)).toBe(false)
  })
})
