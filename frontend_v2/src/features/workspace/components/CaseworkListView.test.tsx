import { fireEvent, render, screen } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import type { CaseworkEntry } from "../casework-api"
import { CaseworkListView } from "./CaseworkListView"

const hooks = vi.hoisted(() => ({
  list: vi.fn(),
}))

vi.mock("../hooks/use-casework", () => ({
  useCaseworkEntries: (...args: unknown[]) => hooks.list(...args),
  useCaseworkAuthors: () => ({ data: [] }),
}))
vi.mock("../hooks/use-current-casework-links", () => ({
  useCurrentCaseworkLinks: () => [],
}))
vi.mock("./CaseworkDetailSheet", () => ({ CaseworkDetailSheet: () => null }))
vi.mock("./CaseworkEditor", () => ({ CaseworkEditor: () => null }))

const finding: CaseworkEntry = {
  id: "finding-1",
  case_id: "case-1",
  entry_type: "finding",
  title: "Transfer occurred after notice",
  body: "The account statement records the transfer.",
  tags: [],
  lifecycle_state: "active",
  significance: "high",
  confidence: null,
  confidence_rationale: null,
  review_state: "accepted",
  version: 1,
  migration_metadata: {},
  needs_migration_review: false,
  links: [],
  updated_at: "2026-09-01T12:00:00Z",
}

describe("CaseworkListView", () => {
  it("lists notes without theory or finding filters", () => {
    render(<CaseworkListView caseId="case-1" entryType="note" canEdit />)
    expect(hooks.list.mock.calls.at(-1)?.[1]).toMatchObject({ entry_type: "note" })
    expect(screen.getByRole("button", { name: "New note" })).toBeVisible()
    expect(screen.queryByText("All lifecycles")).not.toBeInTheDocument()
    expect(screen.queryByText("All confidence")).not.toBeInTheDocument()
  })
  beforeEach(() => {
    hooks.list.mockReset()
    hooks.list.mockReturnValue({
      data: { entries: [finding], total: 26 },
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    })
  })

  it("drives search and pagination through bounded server query parameters", () => {
    render(<CaseworkListView caseId="case-1" entryType="finding" canEdit />)

    expect(hooks.list.mock.calls.at(-1)?.[1]).toMatchObject({
      entry_type: "finding",
      limit: 25,
      offset: 0,
    })

    fireEvent.change(screen.getByPlaceholderText("Search findings"), {
      target: { value: "transfer" },
    })
    expect(hooks.list.mock.calls.at(-1)?.[1]).toMatchObject({
      q: "transfer",
      limit: 25,
      offset: 0,
    })

    fireEvent.click(screen.getByRole("button", { name: /Next/ }))
    expect(hooks.list.mock.calls.at(-1)?.[1]).toMatchObject({
      q: "transfer",
      limit: 25,
      offset: 25,
    })
  })
})
