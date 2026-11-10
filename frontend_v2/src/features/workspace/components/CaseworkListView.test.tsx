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
    expect(hooks.list.mock.calls.at(-1)?.[1]).toMatchObject({
      entry_type: "note",
    })
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

  it("opens with all casework together and changes type without a nested page", () => {
    render(<CaseworkListView caseId="case-1" canEdit />)
    expect(hooks.list.mock.calls.at(-1)?.[1].entry_type).toBeUndefined()
    expect(
      screen.getByRole("button", { name: "All casework" })
    ).toHaveAttribute("aria-pressed", "true")
    expect(screen.getByRole("button", { name: "New casework" })).toBeVisible()
    expect(
      screen.queryByRole("combobox", { name: "Filter by author" })
    ).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "Theories" }))
    expect(hooks.list.mock.calls.at(-1)?.[1]).toMatchObject({
      entry_type: "theory",
      offset: 0,
    })
    expect(screen.getByRole("button", { name: "New theory" })).toBeVisible()
    fireEvent.click(screen.getByRole("button", { name: "Filters" }))
    expect(
      screen.getByRole("combobox", { name: "Filter by confidence" })
    ).toBeVisible()
    fireEvent.click(screen.getByRole("button", { name: "Notes" }))
    expect(
      screen.queryByRole("combobox", { name: "Filter by confidence" })
    ).not.toBeInTheDocument()
    expect(hooks.list.mock.calls.at(-1)?.[1]).toMatchObject({
      entry_type: "note",
      lifecycle_state: undefined,
      confidence_min: undefined,
    })
  })

  it("returns to a populated page after the last item on a later page is removed", () => {
    const view = render(<CaseworkListView caseId="case-1" canEdit />)
    fireEvent.click(screen.getByRole("button", { name: "Next" }))
    expect(hooks.list.mock.calls.at(-1)?.[1].offset).toBe(25)
    hooks.list.mockReturnValue({
      data: { entries: [], total: 25 },
      isLoading: false,
      isError: false,
    })
    view.rerender(<CaseworkListView caseId="case-1" canEdit />)
    expect(hooks.list.mock.calls.at(-1)?.[1].offset).toBe(0)
  })

  it("shows which dossier the work concerns and keeps read-only browsing available", () => {
    hooks.list.mockReturnValue({
      data: {
        entries: [
          {
            ...finding,
            links: [
              {
                id: "link-1",
                target_type: "dossier",
                target_id: "dossier-1",
                target_label: "Northbank Holdings",
                relationship: "context",
              },
            ],
          },
        ],
        total: 1,
      },
      isLoading: false,
      isError: false,
    })
    render(<CaseworkListView caseId="case-1" canEdit={false} />)
    expect(screen.getByText("Northbank Holdings")).toBeVisible()
    expect(
      screen.getByRole("button", { name: /Transfer occurred after notice/ })
    ).toBeEnabled()
    expect(
      screen.queryByRole("button", { name: "New casework" })
    ).not.toBeInTheDocument()
  })

  it("retries a failed list and distinguishes a filtered empty result", () => {
    const retry = vi.fn()
    hooks.list.mockReturnValue({
      isLoading: false,
      isError: true,
      refetch: retry,
    })
    const view = render(<CaseworkListView caseId="case-1" canEdit />)
    fireEvent.click(screen.getByRole("button", { name: "Try again" }))
    expect(retry).toHaveBeenCalledOnce()
    hooks.list.mockReturnValue({
      data: { entries: [], total: 0 },
      isLoading: false,
      isError: false,
    })
    view.rerender(<CaseworkListView caseId="case-1" canEdit />)
    fireEvent.change(screen.getByPlaceholderText("Search casework"), {
      target: { value: "unmatched" },
    })
    expect(screen.getByText("No matching casework")).toBeVisible()
    fireEvent.click(screen.getAllByRole("button", { name: "Clear filters" })[0])
    expect(screen.getByText("No casework yet")).toBeVisible()
  })
})
