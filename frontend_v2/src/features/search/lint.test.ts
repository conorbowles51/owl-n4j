import { ESLint } from "eslint"
import { describe, expect, it } from "vitest"

// The search feature stays clean under the project's lint rules (react-hooks/refs: a ref written during render
// shipped once in SearchDialog and failed `npm run lint`).
describe("search feature lint", () => {
  it("has no eslint errors", async () => {
    const eslint = new ESLint({ cwd: process.cwd() })
    const results = await eslint.lintFiles(["src/features/search"])
    const errors = results.flatMap((r) =>
      r.messages.filter((m) => m.severity === 2).map((m) => `${r.filePath}:${m.line} ${m.ruleId} ${m.message}`),
    )
    expect(errors).toEqual([])
  }, 60_000)
})
