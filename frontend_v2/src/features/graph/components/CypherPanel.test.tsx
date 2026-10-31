import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { CypherPanel } from "./CypherPanel"

function respond(body: unknown, status = 200) {
  vi.mocked(globalThis.fetch).mockResolvedValue(new Response(JSON.stringify(body), { status }))
}

describe("CypherPanel", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn())
    vi.stubGlobal("localStorage", { getItem: vi.fn(() => null), removeItem: vi.fn(), setItem: vi.fn() })
    vi.stubGlobal(
      "ResizeObserver",
      class {
        observe() {}
        unobserve() {}
        disconnect() {}
      }
    )
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  function run(query: string) {
    render(<CypherPanel caseId="case-1" />)
    fireEvent.change(screen.getByRole("textbox"), { target: { value: query } })
    fireEvent.click(screen.getByRole("button", { name: /execute/i }))
  }

  it("posts to the case-scoped query endpoint with the case and shows the rows", async () => {
    respond({
      success: true,
      results: [{ name: "Alpha" }],
      columns: ["name"],
      count: 1,
      row_limit: 500,
      truncated: false,
      total: 1,
      error: null,
    })
    run("MATCH (n {case_id: $case_id}) RETURN n.name AS name")

    expect(await screen.findByText("Alpha")).toBeInTheDocument()
    const [url, options] = vi.mocked(globalThis.fetch).mock.calls[0]
    expect(url).toBe("/api/query")
    expect(options?.method).toBe("POST")
    expect(JSON.parse(options?.body as string)).toEqual({
      query: "MATCH (n {case_id: $case_id}) RETURN n.name AS name",
      case_id: "case-1",
    })
    expect(screen.queryByRole("status")).not.toBeInTheDocument()
  })

  it("says when the answer was cut at the row limit", async () => {
    respond({
      success: true,
      results: [{ name: "Alpha" }],
      columns: ["name"],
      count: 1,
      row_limit: 500,
      truncated: true,
      total: null,
      error: null,
    })
    run("MATCH (n {case_id: $case_id}) RETURN n.name AS name")

    expect(await screen.findByRole("status")).toHaveTextContent("Showing the first 500 rows only")
  })

  it("shows the server's refusal instead of an empty result", async () => {
    respond({
      success: false,
      results: [],
      columns: [],
      count: 0,
      row_limit: 500,
      truncated: false,
      total: null,
      error: "Every MATCH node and relationship must be case-scoped",
    })
    run("MATCH (n) RETURN n")

    await waitFor(() =>
      expect(screen.getByText(/must be case-scoped/)).toBeInTheDocument()
    )
    expect(screen.queryByText("No results")).not.toBeInTheDocument()
  })
})
