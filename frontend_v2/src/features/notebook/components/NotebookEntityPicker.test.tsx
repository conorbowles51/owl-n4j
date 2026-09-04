import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import { graphAPI } from "@/features/graph/api"
import { NotebookEntityPicker } from "./NotebookEntityPicker"

vi.mock("@/features/graph/api", () => ({
  graphAPI: { search: vi.fn() },
}))

describe("NotebookEntityPicker", () => {
  it("searches the current case and attaches a readable entity link", async () => {
    vi.mocked(graphAPI.search).mockResolvedValue({
      nodes: [
        {
          key: "person-1",
          label: "Henry Walsh",
          type: "person",
          properties: {},
        },
      ],
      edges: [],
    })
    const onAttach = vi.fn()
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })

    render(
      <QueryClientProvider client={client}>
        <NotebookEntityPicker caseId="case-1" onAttach={onAttach} />
      </QueryClientProvider>
    )

    fireEvent.change(screen.getByRole("textbox", { name: "Find an entity to link" }), {
      target: { value: "Henry" },
    })
    fireEvent.click(await screen.findByRole("button", { name: /Henry Walsh/ }))

    await waitFor(() => {
      expect(graphAPI.search).toHaveBeenCalledWith("Henry", "case-1", 8)
      expect(onAttach).toHaveBeenCalledWith({
        target_type: "entity",
        target_id: "person-1",
        target_label: "Henry Walsh",
        metadata: { source: "entity_search" },
      })
    })
  })
})
