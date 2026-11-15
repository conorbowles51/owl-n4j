import { fireEvent, render, screen, within } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { beforeEach, expect, it, vi } from "vitest"
import type { CaseworkEntry, CaseworkLink } from "../casework-api"
import { CaseworkDetailSheet } from "./CaseworkDetailSheet"

const hooks = vi.hoisted(() => ({ setRelationship: vi.fn() }))

const link = (over: Partial<CaseworkLink>): CaseworkLink => ({
  id: "l", entry_id: "t1", case_id: "case-1", target_type: "evidence", target_id: "x", target_label: null,
  relationship: "context", source_anchor: {}, metadata: {}, ...over,
})

const entry: CaseworkEntry = {
  id: "t1", case_id: "case-1", entry_type: "theory", title: "Acme pays Ann", body: "Acme pays Ann monthly.", tags: [],
  review_state: "accepted", version: 4, migration_metadata: {}, needs_migration_review: false,
  links: [
    link({ id: "l-pay", target_type: "financial_transaction", target_id: "tx-1", target_label: "2026-01-15 · $500.00 out · ACME",
           relationship: "contradicts" }),
    link({ id: "l-phone", target_type: "phone_record", target_id: "rec-1", target_label: "Call from Ann", relationship: "supports" }),
    link({ id: "l-group", target_type: "financial_selection", target_id: "g-1", target_label: "12 payments", relationship: "supports" }),
    link({ id: "l-old", target_type: "financial_account", target_id: "acct-1", target_label: "Ann's checking", relationship: "unclassified" }),
    link({ id: "l-ctx", target_type: "graph_entity", target_id: "person:ann", target_label: "Ann", relationship: "context" }),
  ],
}

vi.mock("../hooks/use-casework", () => {
  const mutation = () => ({ mutateAsync: vi.fn(), isPending: false })
  return {
    useCaseworkEntry: () => ({ data: entry, isLoading: false, refetch: vi.fn() }),
    useChangeCaseworkLifecycle: mutation, useConvertTheory: mutation, useDeleteCaseworkEntry: mutation,
    useRestoreCaseworkEntry: mutation, useCreateCaseworkEntry: mutation, useUpdateCaseworkEntry: mutation,
    useChangeCaseworkConfidence: mutation, useChangeCaseworkSignificance: mutation,
    useSetLinkRelationship: () => ({ mutate: hooks.setRelationship, isPending: false }),
    useAttachmentOptions: () => ({ data: { items: [] }, isLoading: false }),
    useFindingEvidenceChanges: () => ({ data: undefined }),
  }
})
vi.mock("../hooks/use-current-casework-links", () => ({ useCurrentCaseworkLinks: () => [] }))
vi.mock("@/features/dossiers/hooks", () => ({ useDossiers: () => ({ data: { dossiers: [], total: 0 } }) }))
vi.mock("@/features/phones/link-states", () => ({ useLinkStates: () => ({}), useLinkChoice: () => ({ isPending: false }) }))
vi.mock("@/features/phones/PhoneLinkDetail", () => ({ PhoneLinkDetail: () => null }))

beforeEach(() => hooks.setRelationship.mockReset())

function show(canEdit = true) {
  return render(
    <MemoryRouter>
      <CaseworkDetailSheet caseId="case-1" entryId="t1" open canEdit={canEdit} onOpenChange={vi.fn()} />
    </MemoryRouter>
  )
}

it("compares every link type: a payment against the theory and a group for it are counted with the phone record", () => {
  show()
  expect(screen.getByText(/Compare what supports and contradicts it \(\s*2 for,\s*1 against\)/)).toBeTruthy()
  const against = within(screen.getByTestId("compare-contradicts"))
  expect(against.getByRole("button", { name: /Payment:\s*2026-01-15 · \$500\.00 out · ACME/ })).toBeTruthy()
  const forIt = within(screen.getByTestId("compare-supports"))
  expect(forIt.getByRole("button", { name: /Phone record:\s*Call from Ann/ })).toBeTruthy()
  expect(forIt.getByRole("button", { name: /Ledger selection:\s*12 payments/ })).toBeTruthy()
  expect(screen.getByText(/Also linked as context:\s*1\./)).toBeTruthy()
})

it("lists links saved without a relationship for review and saves the person's choice for exactly that link", () => {
  show()
  const review = within(screen.getByRole("region", { name: "Links to review" }))
  expect(review.getByText(/1\s+link was\s+added without saying how\s+it bears\s+on this theory/)).toBeTruthy()
  expect(review.getByText("Ann's checking")).toBeTruthy()
  fireEvent.click(review.getByRole("button", { name: "Contradicts" }))
  expect(hooks.setRelationship).toHaveBeenCalledWith(
    { entryId: "t1", linkId: "l-old", version: 4, relationship: "contradicts" },
    expect.anything()
  )
})

it("shows a viewer the links to review without the buttons to change them", () => {
  show(false)
  const review = within(screen.getByRole("region", { name: "Links to review" }))
  expect(review.getByText("Ann's checking")).toBeTruthy()
  expect(review.queryByRole("button", { name: "Context" })).toBeNull()
})
