import { describe, expect, it, vi } from "vitest"
import { readingShapeMessage, statementReadingQuery } from "./statement-reading"
import { fetchAPI } from "@/lib/api-client"

vi.mock("@/lib/api-client", () => ({ fetchAPI: vi.fn() }))

describe("a reading the review cannot show", () => {
  it("names the line and value in plain words instead of a schema error", async () => {
    vi.mocked(fetchAPI).mockResolvedValue({
      case_id: "c",
      evidence_file_id: "f",
      rows: [{ id: 1 }],
    } as never)
    const query = statementReadingQuery("c", "f", "", "")
    const error = await query.queryFn().catch((e: Error) => e)
    expect(error).toBeInstanceOf(Error)
    expect((error as Error).message).toMatch(
      /^Loupe read this statement, but the review cannot show /
    )
    expect((error as Error).message).toMatch(
      / and \d+ more\. Nothing was saved or changed\./
    )
    expect((error as Error).message).not.toMatch(/invalid_type|expected/)
  })

  it("lists at most three places", () => {
    const issues = [0, 1, 2, 3, 4].map((n) => ({
      path: ["rows", n, "fields", "balance_derivation"],
    }))
    expect(readingShapeMessage(issues)).toContain(
      'line 3 of the reading, value "balance derivation" and 2 more.'
    )
  })
})
