import { fireEvent, render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import { ConnectionsList } from "./ConnectionsList"

const mocks = vi.hoisted(() => ({ mutateAsync: vi.fn(), marked: new Set<string>() }))

vi.mock("@/features/significant/hooks/use-significant", () => ({
  relationshipMarkKey: (s: string, t: string, d: string) => `${s}|${t}|${d}`,
  useSignificantManifest: () => ({ relationshipKeySet: mocks.marked, isLoading: false }),
  useToggleSignificantRelationship: () => ({ mutateAsync: mocks.mutateAsync, isPending: false }),
}))
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }))

const connections = [
  {
    relationshipType: "DIRECTOR_OF",
    nodes: [
      { key: "acme", label: "Acme", type: "Company", direction: "outgoing" as const },
      { key: "bob", label: "Bob", type: "Person", direction: "incoming" as const },
    ],
  },
]

describe("ConnectionsList relationship marks (GR-01)", () => {
  it("marks each relationship in its own direction from the entity panel", async () => {
    mocks.mutateAsync.mockResolvedValue({ added_relationship_count: 1 })
    render(<ConnectionsList connections={connections} caseId="case-1" entity={{ key: "ann", label: "Ann" }} />)
    fireEvent.click(screen.getByRole("button", { name: "Mark relationship significant: Ann director of Acme" }))
    fireEvent.click(screen.getByRole("button", { name: "Mark relationship significant: Bob director of Ann" }))
    expect(mocks.mutateAsync.mock.calls.map((c) => c[0].relationship)).toEqual([
      { source_key: "ann", type: "DIRECTOR_OF", target_key: "acme" },
      { source_key: "bob", type: "DIRECTOR_OF", target_key: "ann" },
    ])
    expect(mocks.mutateAsync.mock.calls[0][0]).toMatchObject({ significant: true, surface: "entity_panel" })
  })

  it("shows a marked relationship as marked and unmarks it", () => {
    mocks.mutateAsync.mockReset().mockResolvedValue({ removed_relationship_count: 1 })
    mocks.marked = new Set(["ann|DIRECTOR_OF|acme"])
    render(<ConnectionsList connections={connections} caseId="case-1" entity={{ key: "ann", label: "Ann" }} />)
    const button = screen.getByRole("button", { name: "Remove relationship from Significant: Ann director of Acme" })
    expect(button.getAttribute("aria-pressed")).toBe("true")
    fireEvent.click(button)
    expect(mocks.mutateAsync.mock.calls[0][0]).toMatchObject({ significant: false })
    mocks.marked = new Set()
  })

  it("offers no mark where the panel has no case (the comparison dialog)", () => {
    render(<ConnectionsList connections={connections} />)
    expect(screen.queryByRole("button", { name: /relationship/ })).toBeNull()
  })
})
