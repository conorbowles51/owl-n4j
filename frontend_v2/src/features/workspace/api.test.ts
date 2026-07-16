import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { workspaceAPI } from "./api"

describe("workspaceAPI findings", () => {
  const originalFetch = globalThis.fetch

  beforeEach(() => {
    globalThis.fetch = vi.fn()
    localStorage.clear()
  })

  afterEach(() => {
    globalThis.fetch = originalFetch
  })

  it("maps linked file metadata when listing findings", async () => {
    vi.mocked(globalThis.fetch).mockResolvedValue(
      new Response(
        JSON.stringify({
          findings: [
            {
              finding_id: "finding_1",
              title: "Source-backed finding",
              linked_evidence: [
                {
                  id: "file-1",
                  original_filename: "ledger.pdf",
                  summary: "Ledger summary",
                  url: "/api/evidence/file-1/file",
                },
              ],
            },
          ],
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    )

    const findings = await workspaceAPI.getFindings("case-1")

    expect(findings[0].id).toBe("finding_1")
    expect(findings[0].linked_evidence?.[0].summary).toBe("Ledger summary")
  })

  it("sends the complete active finding order", async () => {
    vi.mocked(globalThis.fetch).mockResolvedValue(
      new Response(JSON.stringify({ findings: [] }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    )

    await workspaceAPI.reorderFindings("case-1", ["finding_2", "finding_1"])

    expect(globalThis.fetch).toHaveBeenCalledWith(
      "/api/workspace/case-1/findings/reorder",
      expect.objectContaining({
        method: "PUT",
        body: JSON.stringify({ finding_ids: ["finding_2", "finding_1"] }),
      }),
    )
  })
})
