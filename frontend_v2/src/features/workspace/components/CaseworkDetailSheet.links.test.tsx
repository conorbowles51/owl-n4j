import { fireEvent, render, screen } from "@testing-library/react"
import { MemoryRouter, useLocation } from "react-router-dom"
import { beforeEach, expect, it, vi } from "vitest"
import type { CaseworkEntry } from "../casework-api"
import { CaseworkDetailSheet } from "./CaseworkDetailSheet"

const dossiersFixture = vi.hoisted(() => ({ total: 0 }))
beforeEach(() => {
  dossiersFixture.total = 0
})

const entry: CaseworkEntry = {
  id: "note-1",
  case_id: "case-1",
  entry_type: "note",
  body: "Follow up with the witness before the review date.",
  tags: [],
  review_state: "accepted",
  version: 1,
  migration_metadata: {},
  needs_migration_review: false,
  links: [
    {
      id: "link-event",
      entry_id: "note-1",
      case_id: "case-1",
      target_type: "timeline_event",
      target_id: "event/review date",
      target_label: "First site visit",
      relationship: "context",
      source_anchor: {},
      metadata: {},
    },
    {
      id: "link-task",
      entry_id: "note-1",
      case_id: "case-1",
      target_type: "task",
      target_id: "task-1",
      target_label: "Contact the witness",
      relationship: "context",
      source_anchor: {},
      metadata: {},
    },
    {
      id: "link-deadline",
      entry_id: "note-1",
      case_id: "case-1",
      target_type: "deadline",
      target_id: "deadline-1",
      target_label: "Review date",
      relationship: "context",
      source_anchor: {},
      metadata: {},
    },
  ],
}
vi.mock("../hooks/use-casework", () => {
  const mutation = () => ({ mutateAsync: vi.fn(), isPending: false })
  return {
    useCaseworkEntry: () => ({ data: entry, isLoading: false }),
    useChangeCaseworkLifecycle: mutation,
    useConvertTheory: mutation,
    useDeleteCaseworkEntry: mutation,
    useRestoreCaseworkEntry: mutation,
  }
})
vi.mock("../hooks/use-current-casework-links", () => ({
  useCurrentCaseworkLinks: () => [],
}))
vi.mock("@/features/dossiers/hooks", () => ({
  useDossiers: ({
    offset = 0,
    limit = 10,
  }: {
    offset?: number
    limit?: number
  }) => ({
    data: {
      dossiers: Array.from({ length: dossiersFixture.total }, (_, index) => ({
        id: `dossier-${index + 1}`,
        display_name: `Collected dossier ${index + 1}`,
      })).slice(offset, offset + limit),
      total: dossiersFixture.total,
    },
  }),
}))
vi.mock("@/features/phones/link-states", () => ({
  useLinkStates: () => ({}),
  useLinkChoice: () => ({ isPending: false }),
}))

function Where() {
  const location = useLocation()
  return (
    <span data-testid="linked-work-route">
      {location.pathname + location.search}
    </span>
  )
}

it.each([
  ["Contact the witness", "workspace?view=work&item=task-1"],
  ["Review date", "workspace?view=work&item=deadline-1"],
  ["First site visit", "timeline?event=event%2Freview%20date"],
])(
  "opens linked %s for a viewer and respects an underlying unsaved draft",
  (label, destination) => {
    const guard = vi.fn().mockReturnValue(false)
    render(
      <MemoryRouter initialEntries={["/cases/case-1/workspace?view=casework"]}>
        <CaseworkDetailSheet
          caseId="case-1"
          entryId="note-1"
          open
          canEdit={false}
          onOpenChange={vi.fn()}
          onBeforeNavigate={guard}
        />
        <Where />
      </MemoryRouter>
    )
    const button = screen.getByRole("button", { name: new RegExp(label) })
    expect(button).toBeEnabled()
    fireEvent.click(button)
    expect(guard).toHaveBeenCalledOnce()
    expect(screen.getByTestId("linked-work-route")).toHaveTextContent(
      "/cases/case-1/workspace?view=casework"
    )
    guard.mockReturnValue(true)
    fireEvent.click(button)
    expect(screen.getByTestId("linked-work-route")).toHaveTextContent(
      `/cases/case-1/${destination}`
    )
  }
)

it("returns to the remaining dossiers after the last membership on a later page is removed", () => {
  dossiersFixture.total = 11
  const view = (
    <MemoryRouter>
      <CaseworkDetailSheet
        caseId="case-1"
        entryId="note-1"
        open
        canEdit={false}
        onOpenChange={vi.fn()}
      />
    </MemoryRouter>
  )
  const { rerender } = render(view)
  fireEvent.click(screen.getByRole("button", { name: "Next" }))
  expect(
    screen.getByRole("button", { name: "Collected dossier 11" })
  ).toBeInTheDocument()
  expect(
    screen.queryByRole("button", { name: "Collected dossier 1" })
  ).not.toBeInTheDocument()

  dossiersFixture.total = 10
  rerender(
    <MemoryRouter>
      <CaseworkDetailSheet
        caseId="case-1"
        entryId="note-1"
        open
        canEdit={false}
        onOpenChange={vi.fn()}
      />
    </MemoryRouter>
  )
  expect(
    screen.getByRole("button", { name: "Collected dossier 1" })
  ).toBeInTheDocument()
  expect(
    screen.getByRole("button", { name: "Collected dossier 10" })
  ).toBeInTheDocument()
  expect(
    screen.queryByRole("button", { name: "Collected dossier 11" })
  ).not.toBeInTheDocument()
  expect(
    screen.queryByRole("navigation", { name: "Containing dossiers pagination" })
  ).not.toBeInTheDocument()
})
