/** Dossier sheet layout (unit). Mocks follow DossierDetailSheet.browser.test.tsx. */
import { fireEvent, render, screen } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { MemoryRouter } from "react-router-dom"
import { beforeEach, afterEach, describe, expect, it, vi } from "vitest"
import type { Dossier } from "../api"
import { DossierDetailSheet } from "./DossierDetailSheet"
vi.mock("@/lib/protected-file", () => ({
  useProtectedObjectUrl: () => ({
    objectUrl: "/mock-source.pdf",
    loading: false,
    error: null,
  }),
  openProtectedFile: vi.fn(),
}))

vi.mock("@/features/workspace/hooks/use-casework", () => ({
  useAttachmentOptions: () => ({
    isLoading: false,
    data: {
      items: [
        {
          target_id: "evidence-1",
          label: `${"long_filename_".repeat(25)}.png`,
          description: "A lengthy evidence summary. ".repeat(100),
        },
      ],
    },
  }),
}))

const fixture: Dossier = {
  id: "dossier-1",
  case_id: "case-1",
  dossier_type: "person",
  display_name: "Henry Current",
  display_name_snapshot: "Henry Old",
  summary: "Central subject in the asset transfers.",
  importance: "Primary subject",
  canonical_entity_key: "person:henry",
  linkage_state: "linked",
  status: "active",
  needs_link_review: false,
  graph_entity_deleted: false,
  canonical_identity: {
    key: "person:henry",
    name: "Henry Current",
    type: "Person",
    summary:
      "## Background\n\nGraph-grounded identity summary\n\n- **Procurement manager**\n- Linked to transfers\n\n[Report, p.2](doc://report.pdf/2)",
    verified_facts: [{ text: "fact" }],
  },
  roles: [
    { id: "role-1", name: "Subject", is_builtin: true },
    { id: "role-2", name: "Client", is_builtin: true },
  ],
  links: [],
  media: [],
  assessments: [
    {
      id: "assessment-1",
      category: "credibility",
      content: "Account conflicts with the timestamped record.",
      author_user_id: "user-1",
      supporting_links: [],
      assessment_date: "2026-08-20",
    },
  ],
  interviews: [
    {
      id: "interview-1",
      interview_date: "2026-08-21T10:00:00Z",
      participants: ["Henry Current"],
      interviewer_user_ids: [],
      status: "completed",
      working_notes: "Follow-up on ownership structure.",
      evidence_links: [
        {
          id: "link-1",
          evidence_file_id: "evidence-1",
          source_anchor: { page: 2 },
          evidence: {
            id: "evidence-1",
            original_filename: "interview.pdf",
            status: "processed",
            size: 100,
            sha256: "abc",
            metadata: {},
            file_url: "/api/evidence/evidence-1/file",
          },
        },
      ],
      created_by_user_id: "user-1",
    },
  ],
}

vi.mock("../hooks", () => ({
  useDossier: () => ({ data: fixture, isLoading: false, refetch: vi.fn() }),
  useDossierMutation: () => ({
    mutate: vi.fn(),
    mutateAsync: vi.fn(),
    isPending: false,
  }),
}))
vi.mock("./RemovedFromDossier", () => ({
  RemovedFromDossier: () => <details>Removed from this dossier (1)</details>,
}))
vi.mock("./EvidenceImage", () => ({
  EvidenceImage: () => <div data-testid="evidence-image" />,
}))
vi.mock("@/features/notebook/components/NotebookEntityPicker", () => ({
  NotebookEntityPicker: () => <div>Entity picker</div>,
}))
vi.mock("@/features/workspace-ai/components/WorkspaceAIPanel", () => ({
  WorkspaceAIPanel: () => <div>Cited AI assistance</div>,
}))

beforeEach(() => {
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const url = String(input)
    if (/\/page\/\d+\/image/.test(url))
      return new Response(
        Uint8Array.from(
          atob(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+j9n0AAAAASUVORK5CYII="
          ),
          (c) => c.charCodeAt(0)
        ),
        { headers: { "Content-Type": "image/png", "X-PDF-Page-Count": "2" } }
      )
    if (url.endsWith("/api/evidence/evidence-1"))
      return new Response(
        JSON.stringify({
          id: "evidence-1",
          original_filename: "interview.pdf",
          transcription_segments: [],
        }),
        { headers: { "Content-Type": "application/json" } }
      )
    return new Response("Not found", { status: 404 })
  })
})
afterEach(() => vi.restoreAllMocks())

function renderDetail(canEdit = true) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <DossierDetailSheet
          caseId="case-1"
          dossierId="dossier-1"
          open
          canEdit={canEdit}
          onOpenChange={vi.fn()}
        />
      </MemoryRouter>
    </QueryClientProvider>
  )
}

describe("Dossier detail layout", () => {
  it("never lets the tabs shrink under the block that follows them", () => {
    // The sheet is a fixed-height flex column. A tabs block allowed to shrink below its content lets the last
    // interview cards spill underneath "Removed from this dossier", hiding their evidence links (seen on live).
    renderDetail()
    fireEvent.mouseDown(screen.getByRole("tab", { name: "Interviews" }))
    const tabs = screen.getByRole("tablist").closest('[data-slot="tabs"]') as HTMLElement
    expect(tabs).not.toBeNull()
    expect(tabs.className).toContain("shrink-0")
    expect(tabs.className).not.toContain("min-h-0")
  })
})
