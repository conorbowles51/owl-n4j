import { fireEvent, render, screen } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { MemoryRouter } from "react-router-dom"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"
import type { Dossier } from "../api"
import { DossierDetailSheet } from "./DossierDetailSheet"
import { page } from "vitest/browser"
import "@/styles/globals.css"
vi.mock("@/lib/protected-file", () => ({
  useProtectedObjectUrl: () => ({ objectUrl: "/mock-source.pdf", loading: false, error: null }),
  openProtectedFile: vi.fn(),
}))

vi.mock("@/features/workspace/hooks/use-casework", () => ({
  useAttachmentOptions: () => ({
    isLoading: false,
    data: { items: [{ target_id: "evidence-1", label: `${"long_filename_".repeat(25)}.png`, description: "A lengthy evidence summary. ".repeat(100) }] },
  }),
}))

const fixture: Dossier = {
  id: "dossier-1", case_id: "case-1", dossier_type: "person", display_name: "Henry Current", display_name_snapshot: "Henry Old",
  summary: "Central subject in the asset transfers.", importance: "Primary subject", canonical_entity_key: "person:henry", linkage_state: "linked", status: "active", needs_link_review: false, graph_entity_deleted: false,
  canonical_identity: { key: "person:henry", name: "Henry Current", type: "Person", summary: "## Background\n\nGraph-grounded identity summary\n\n- **Procurement manager**\n- Linked to transfers\n\n[Report, p.2](doc://report.pdf/2)", verified_facts: [{ text: "fact" }] },
  roles: [{ id: "role-1", name: "Subject", is_builtin: true }, { id: "role-2", name: "Client", is_builtin: true }],
  links: [], media: [],
  assessments: [{ id: "assessment-1", category: "credibility", content: "Account conflicts with the timestamped record.", author_user_id: "user-1", supporting_links: [], assessment_date: "2026-08-20" }],
  interviews: [{ id: "interview-1", interview_date: "2026-08-21T10:00:00Z", participants: ["Henry Current"], interviewer_user_ids: [], status: "completed", working_notes: "Follow-up on ownership structure.", evidence_links: [{ id: "link-1", evidence_file_id: "evidence-1", source_anchor: { page: 2 }, evidence: { id: "evidence-1", original_filename: "interview.pdf", status: "processed", size: 100, sha256: "abc", metadata: {}, file_url: "/api/evidence/evidence-1/file" } }], created_by_user_id: "user-1" }],
}

vi.mock("../hooks", () => ({
  useDossier: () => ({ data: fixture, isLoading: false, refetch: vi.fn() }),
  useDossierMutation: () => ({ mutate: vi.fn(), mutateAsync: vi.fn(), isPending: false }),
}))
vi.mock("./EvidenceImage", () => ({ EvidenceImage: () => <div data-testid="evidence-image" /> }))
vi.mock("@/features/notebook/components/NotebookEntityPicker", () => ({ NotebookEntityPicker: () => <div>Entity picker</div> }))
vi.mock("@/features/workspace-ai/components/WorkspaceAIPanel", () => ({ WorkspaceAIPanel: () => <div>Cited AI assistance</div> }))

function renderDetail(canEdit = true) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={client}><MemoryRouter><DossierDetailSheet caseId="case-1" dossierId="dossier-1" open canEdit={canEdit} onOpenChange={vi.fn()} /></MemoryRouter></QueryClientProvider>)
}

describe("Dossier detail in Chromium", () => {
  it("puts original interviews first and opens their documents over the dossier", async () => {
    const user = userEvent.setup()
    renderDetail()
    await user.click(screen.getByRole("tab", { name: "Interviews" }))
    const source = screen.getByRole("button", { name: "interview.pdf" })
    expect(screen.queryByText("completed")).not.toBeInTheDocument()
    expect(source.compareDocumentPosition(screen.getByText("Cited AI assistance")) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    await user.click(source)
    expect(screen.getByRole("dialog", { name: "interview.pdf" })).toBeVisible()
    expect(document.querySelector("iframe")?.getAttribute("src")).toContain("#page=2")
    await user.keyboard("{Escape}")
    expect(screen.queryByRole("dialog", { name: "interview.pdf" })).not.toBeInTheDocument()
    expect(screen.getByRole("tab", { name: "Interviews" })).toHaveAttribute("data-state", "active")
    expect(screen.getByText("Follow-up on ownership structure.")).toBeVisible()
  })
  for (const width of [1280, 390]) {
    for (const [tab, trigger, title, action] of [
      ["Media", "Add image", "Add evidence-backed image", "Add image"],
      ["Assessments", "Assessment", "Record investigator assessment", "Record assessment"],
      ["Interviews", "Interview", "Add interview or statement", "Add interview"],
    ]) {
      it(`keeps ${tab} controls inside the dialog at ${width}px`, async () => {
        await page.viewport(width, 720)
        const user = userEvent.setup()
        renderDetail()
        await user.click(screen.getByRole("tab", { name: tab }))
        await user.click(screen.getByRole("button", { name: trigger }))
        const dialog = await screen.findByRole("dialog", { name: title })
        if (tab === "Interviews") {
          expect(screen.queryByText("Status")).not.toBeInTheDocument()
          expect(screen.getByRole("button", { name: "Add interview" })).toBeDisabled()
        }
        await expect.poll(() => dialog.getBoundingClientRect().width).toBeGreaterThan(300)
        expect(dialog.scrollWidth).toBeLessThanOrEqual(dialog.clientWidth)
        const bounds = dialog.getBoundingClientRect()
        expect(bounds.left).toBeGreaterThanOrEqual(0)
        expect(bounds.right).toBeLessThanOrEqual(width)
        expect(bounds.height).toBeLessThanOrEqual(720)
        await user.click(screen.getByRole("button", { name: "Add" }))
        expect(dialog.scrollWidth).toBeLessThanOrEqual(dialog.clientWidth)
        const save = screen.getByRole("button", { name: action })
        if (tab === "Interviews") expect(save).toBeEnabled()
        save.scrollIntoView({ block: "nearest" })
        const saveBounds = save.getBoundingClientRect()
        expect(saveBounds.left).toBeGreaterThanOrEqual(bounds.left)
        expect(saveBounds.right).toBeLessThanOrEqual(bounds.right)
        expect(saveBounds.bottom).toBeLessThanOrEqual(720)
        await user.click(screen.getByRole("button", { name: "Cancel" }))
        expect(screen.queryByRole("dialog", { name: title })).not.toBeInTheDocument()
      })
    }
  }
  it("separates canonical identity from investigator-authored analysis", async () => {
    const user = userEvent.setup()
    renderDetail()
    expect(screen.getByText("Henry Current")).toBeVisible()
    expect(screen.getByText("Graph linked")).toBeVisible()
    expect(screen.getByText("Canonical graph identity")).toBeVisible()
    expect(screen.getByText("Graph-grounded identity summary")).toBeVisible()
    expect(screen.queryByText("person:henry")).not.toBeInTheDocument()
    expect(screen.getByRole("heading", { name: "Background", level: 2 })).toBeVisible()
    expect(screen.getByText("Procurement manager").tagName).toBe("STRONG")
    expect(screen.getByText("Linked to transfers").tagName).toBe("LI")
    expect(screen.getByRole("button", { name: "Report, p.2" })).toBeVisible()
    await user.click(screen.getByRole("tab", { name: "Assessments" }))
    expect(await screen.findByText("Account conflicts with the timestamped record.")).toBeVisible()
    expect(screen.getByText(/not objective identity facts/i)).toBeVisible()
    await user.click(screen.getByRole("tab", { name: "Interviews" }))
    expect(await screen.findByText("Follow-up on ownership structure.")).toBeVisible()
  })
  it("removes all mutation affordances for a viewer", () => {
    renderDetail(false)
    expect(screen.queryByRole("button", { name: /Dossier actions/i })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole("tab", { name: "Media" }))
    expect(screen.queryByRole("button", { name: /Add image/i })).not.toBeInTheDocument()
  })
})
