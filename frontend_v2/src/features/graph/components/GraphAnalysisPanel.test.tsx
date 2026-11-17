import { render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

const idle = { mutate: vi.fn(), isPending: false, data: undefined }
vi.mock("../hooks/use-graph-analysis", () => ({
  usePageRank: () => idle,
  useLouvainCommunities: () => idle,
  useBetweennessCentrality: () => idle,
  useShortestPaths: () => idle,
}))

import { GraphAnalysisPanel } from "./GraphAnalysisPanel"

describe("GraphAnalysisPanel", () => {
  it("names each result by what it finds and says what its number means, never by the method", () => {
    render(<GraphAnalysisPanel caseId="case-1" scope="all" />)
    expect(screen.getByText("Most connected items")).toBeTruthy()
    expect(screen.getByText("Groups that link mostly among themselves")).toBeTruthy()
    expect(screen.getByText("Items that link otherwise separate groups")).toBeTruthy()
    expect(screen.getByText(/It is not a count of links/)).toBeTruthy()
    expect(screen.getByText(/how many items each group holds/)).toBeTruthy()
    expect(screen.getByText(/more of those routes pass through the item/)).toBeTruthy()
    const text = document.body.textContent || ""
    for (const jargon of ["PageRank", "Communities", "Betweenness", "Graph Analysis", "nodes", "hops"]) {
      expect(text).not.toContain(jargon)
    }
  })
})
