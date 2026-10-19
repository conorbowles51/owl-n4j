import { render, screen, within, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { MemoryRouter, useLocation } from "react-router-dom"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { page } from "vitest/browser"
import { CaseworkListView } from "@/features/workspace/components/CaseworkListView"
import { DossierDetailSheet } from "./DossierDetailSheet"
import { DossierCreateSheet } from "./DossierCreateSheet"
import { AddEvidenceToDossierDialog } from "./AddEvidenceToDossierDialog"
import type { Dossier } from "../api"
import "@/styles/globals.css"

vi.mock("@/features/workspace-ai/components/WorkspaceAIPanel", () => ({
  WorkspaceAIPanel: () => <p>Review interview proposals</p>,
}))
vi.mock("@/lib/protected-file", () => ({
  useProtectedObjectUrl: () => ({
    objectUrl: "/synthetic-source",
    loading: false,
    error: null,
  }),
  openProtectedFile: vi.fn(),
}))

let dossier: Dossier
let workspaceLinkJourney: boolean
let failSave: boolean
let listTotal: number
let requests: Array<{
  url: string
  method: string
  body: Record<string, unknown>
}>
const json = (value: unknown, status = 200) =>
  new Response(JSON.stringify(value), {
    status,
    headers: { "Content-Type": "application/json" },
  })

beforeEach(() => {
  workspaceLinkJourney = false
  failSave = false
  listTotal = 1
  requests = []
  dossier = {
    id: "dossier-1",
    case_id: "case-1",
    dossier_type: "person",
    display_name: "Witness Example",
    display_name_snapshot: "Witness Example",
    summary: "Investigator's own brief",
    linkage_state: "unlinked",
    status: "active",
    needs_link_review: false,
    graph_entity_deleted: false,
    roles: [],
    contacts: [],
    media: [],
    links: [
      {
        id: "source-link",
        target_type: "evidence",
        target_id: "evidence-1",
        label: "statement.pdf",
        source_anchor: { page: 2 },
      },
      {
        id: "note-link",
        target_type: "entry",
        target_id: "entry-1",
        label: "Witness follow-up",
        source_anchor: {},
      },
    ],
    assessments: [
      {
        id: "summary-1",
        category: "statement_summary",
        content: "Reviewed account of the meeting.",
        provenance_type: "ai_assisted",
        created_at: "2026-10-01T12:00:00Z",
        supporting_links: [
          {
            id: "summary-source",
            target_type: "evidence",
            target_id: "evidence-1",
            label: "Accepted summary source",
            source_anchor: { page: 2 },
          },
        ],
      },
    ],
    interviews: [
      {
        id: "interview-1",
        date_value: "2025-07",
        interview_date: null,
        participants: ["Witness Example"],
        interviewer_user_ids: [],
        status: "completed",
        working_notes: "Original interview notes",
        evidence_links: [
          {
            id: "interview-source",
            evidence_file_id: "evidence-1",
            source_anchor: { page: 2 },
            evidence: {
              id: "evidence-1",
              original_filename: "statement.pdf",
              status: "processed",
              size: 10,
              sha256: "synthetic",
              metadata: {},
              file_url: "/api/evidence/evidence-1/file",
            },
          },
        ],
      },
    ],
  }
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input)
    const method = init?.method ?? "GET"
    const body = init?.body ? JSON.parse(String(init.body)) : {}
    requests.push({ url, method, body })
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
    if (url.includes("attachment-options"))
      return json({
        items: [
          {
            target_id: "evidence-2",
            target_type: "evidence",
            label: "new-statement.pdf",
            description: "Synthetic test source",
          },
        ],
      })
    if (url.includes("/api/evidence/"))
      return json({
        id: url.split("/").pop(),
        case_id: "case-1",
        original_filename: "statement.pdf",
        transcription_segments: [],
      })
    if (url.startsWith("/api/dossiers?"))
      return json({
        dossiers: [dossier],
        total: listTotal,
        offset: Number(
          new URL(url, "http://test").searchParams.get("offset") ?? 0
        ),
        limit: 50,
      })
    if (url === "/api/dossiers/dossier-1" && method === "PATCH") {
      if (failSave) return json({ detail: "Temporary save failure" }, 503)
      Object.assign(dossier, body)
      return json(dossier)
    }
    if (url === "/api/dossiers/dossier-1") return json(dossier)
    if (url.endsWith("/dossier-1/evidence") && method === "POST") {
      for (const id of body.evidence_file_ids as string[])
        if (!dossier.links!.some((link) => link.target_id === id))
          dossier.links!.push({
            id: `link-${id}`,
            target_type: "evidence",
            target_id: id,
            label: "new-statement.pdf",
            source_anchor: {},
          })
      return json(dossier)
    }
    if (url.endsWith("/interviews/interview-1") && method === "PATCH") {
      const interview = dossier.interviews![0]
      Object.assign(interview, body, {
        evidence_links: interview.evidence_links,
      })
      return json(interview)
    }
    if (url.endsWith("/interviews/interview-1") && method === "DELETE") {
      dossier.interviews = []
      return new Response(null, { status: 204 })
    }
    if (url.includes("/entries/authors")) return json({ authors: [] })
    if (/\/entries\?/.test(url)) return json({ entries: [{ id: "entry-1", entry_type: "note", title: "Witness follow-up", body: "Follow up on the recorded discrepancy.", tags: [], links: [], review_state: "accepted", version: 1 }], total: 1 })
    if (url.includes("/entries/entry-1") && !url.includes("history"))
      return json({
        id: "entry-1",
        case_id: "case-1",
        entry_type: "note",
        title: "Witness follow-up",
        body: "Follow up on the recorded discrepancy.",
        version: 1,
        review_state: "accepted",
        tags: [],
        links: workspaceLinkJourney ? [ { id: "source", target_type: "evidence", target_id: "evidence-1", target_label: "Original statement source", relationship: "context", source_anchor: { page: 2 } }, { id: "subject", target_type: "dossier", target_id: "dossier-1", target_label: "Witness dossier", relationship: "context", source_anchor: {} } ] : [],
        needs_migration_review: false,
      })
    if (url.includes("history"))
      return json({ revisions: [], events: [], total: 0 })
    return json({ detail: "No synthetic route" }, 404)
  })
})
afterEach(() => vi.restoreAllMocks())

function LocationProbe() {
  const location = useLocation()
  return (
    <output aria-label="location">
      {location.pathname}
      {location.search}
    </output>
  )
}
function renderDossier(canEdit = true) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter
        initialEntries={["/cases/case-1/dossiers?dossier=dossier-1"]}
      >
        <DossierDetailSheet
          caseId="case-1"
          dossierId="dossier-1"
          open
          canEdit={canEdit}
          onOpenChange={vi.fn()}
        />
        <LocationProbe />
      </MemoryRouter>
    </QueryClientProvider>
  )
}

describe("Connected dossier workflows", () => {
  it("opens an accepted summary's source at its page and returns to the Brief", async () => {
    const user = userEvent.setup()
    await page.viewport(1280, 1000)
    renderDossier()
    expect(
      await screen.findByText("Reviewed account of the meeting.")
    ).toBeVisible()
    expect(
      screen.getByRole("textbox", { name: "Investigator brief" })
    ).toHaveValue("Investigator's own brief")
    if (import.meta.env.VITE_DOSSIER_CAPTURE_DIR)
      await page.screenshot({
        path: `${import.meta.env.VITE_DOSSIER_CAPTURE_DIR}/dossier-brief.png`,
      })
    await user.click(
      screen.getByRole("button", { name: "Accepted summary source" })
    )
    expect(
      await screen.findByRole("img", { name: "Page 2 of the original PDF" })
    ).toBeVisible()
    await user.keyboard("{Escape}")
    expect(screen.getByRole("tab", { name: "Brief" })).toHaveAttribute(
      "data-state",
      "active"
    )
    expect(screen.getByLabelText("location")).toHaveTextContent(
      "/cases/case-1/dossiers?dossier=dossier-1"
    )
  })

  it("opens linked notes over the dossier without changing the route", async () => {
    const user = userEvent.setup()
    renderDossier()
    await user.click(
      await screen.findByRole("button", { name: "Witness follow-up" })
    )
    expect(
      await screen.findByText("Follow up on the recorded discrepancy.")
    ).toBeVisible()
    await user.keyboard("{Escape}")
    expect(screen.getByRole("tab", { name: "Brief" })).toBeVisible()
    expect(screen.getByLabelText("location")).toHaveTextContent(
      "?dossier=dossier-1"
    )
  })

  it("adds evidence from the Brief and retains existing casework links", async () => {
    const user = userEvent.setup()
    renderDossier()
    await user.click(
      await screen.findByRole("button", { name: "Add evidence" })
    )
    const dialog = screen.getByRole("dialog", {
      name: "Add evidence to Witness Example",
    })
    await user.click(await within(dialog).findByRole("button", { name: "Add" }))
    await user.click(
      within(dialog).getByRole("button", { name: "Link 1 file" })
    )
    await waitFor(() =>
      expect(
        screen.queryByRole("dialog", {
          name: "Add evidence to Witness Example",
        })
      ).not.toBeInTheDocument()
    )
    expect(
      screen.getByRole("button", { name: "new-statement.pdf" })
    ).toBeVisible()
    expect(
      screen.getByRole("button", { name: "Witness follow-up" })
    ).toBeVisible()
    expect(
      requests.some(
        (request) => request.method === "PUT" && request.url.endsWith("/links")
      )
    ).toBe(false)
  })

  it("keeps a failed brief save and unsaved writing through tab changes", async () => {
    const user = userEvent.setup()
    renderDossier()
    const brief = await screen.findByRole("textbox", {
      name: "Investigator brief",
    })
    await user.clear(brief)
    await user.type(brief, "Revised investigator analysis")
    await user.click(screen.getByRole("tab", { name: "Interviews" }))
    await user.click(screen.getByRole("tab", { name: "Brief" }))
    expect(
      screen.getByRole("textbox", { name: "Investigator brief" })
    ).toHaveValue("Revised investigator analysis")
    failSave = true
    await user.click(screen.getByRole("button", { name: "Save brief" }))
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Your writing is kept"
    )
    failSave = false
    await user.click(screen.getByRole("button", { name: "Retry save" }))
    await waitFor(() =>
      expect(screen.getByRole("status")).toHaveTextContent("Saved")
    )
    expect(dossier.summary).toBe("Revised investigator analysis")
    expect(screen.getByText("Reviewed account of the meeting.")).toBeVisible()
  })

  it("protects unsaved brief changes when closing the dossier", async () => {
    const user = userEvent.setup()
    renderDossier()
    const brief = await screen.findByRole("textbox", {
      name: "Investigator brief",
    })
    await user.type(brief, " Additional unsaved detail")
    await user.click(screen.getByRole("button", { name: "Close" }))
    const warning = screen.getByRole("dialog", { name: "Unsaved brief" })
    expect(warning).toBeVisible()
    await user.click(
      within(warning).getByRole("button", { name: "Keep editing" })
    )
    expect(
      screen.getByRole("textbox", { name: "Investigator brief" })
    ).toHaveValue("Investigator's own brief Additional unsaved detail")
    expect(requests.some((request) => request.method === "PATCH")).toBe(false)
  })

  it("edits a month-only interview without inventing a day", async () => {
    const user = userEvent.setup()
    renderDossier()
    await user.click(await screen.findByRole("tab", { name: "Interviews" }))
    await user.click(screen.getByRole("button", { name: /Edit interview/ }))
    const dialog = screen.getByRole("dialog", {
      name: "Edit interview or statement",
    })
    expect(within(dialog).getByLabelText("Date precision")).toHaveValue("month")
    expect(within(dialog).getByLabelText("Month and year")).toHaveValue(
      "2025-07"
    )
    await user.clear(within(dialog).getByLabelText("Working notes"))
    await user.type(
      within(dialog).getByLabelText("Working notes"),
      "Updated interview notes"
    )
    await user.click(
      within(dialog).getByRole("button", { name: "Save interview" })
    )
    await waitFor(() =>
      expect(dossier.interviews![0].working_notes).toBe(
        "Updated interview notes"
      )
    )
    const saved = requests.find(
      (request) =>
        request.method === "PATCH" && request.url.includes("/interviews/")
    )!
    expect(saved.body.date_value).toBe("2025-07")
    expect(saved.body).not.toHaveProperty("interview_date")
    expect(saved.body.evidence_links).toEqual([
      { evidence_file_id: "evidence-1", source_anchor: { page: 2 } },
    ])
  })

  it("confirms interview removal and retains accepted summaries and evidence", async () => {
    const user = userEvent.setup()
    renderDossier()
    await user.click(await screen.findByRole("tab", { name: "Interviews" }))
    await user.click(
      screen.getByRole("button", { name: /Remove interview July/ })
    )
    const dialog = screen.getByRole("dialog", {
      name: "Remove interview from dossier?",
    })
    expect(
      within(dialog).getByText(
        /Original evidence files and accepted assessments remain saved/
      )
    ).toBeVisible()
    await user.click(
      within(dialog).getByRole("button", { name: "Remove interview" })
    )
    expect(
      await screen.findByText("No interviews or statements recorded.")
    ).toBeVisible()
    await user.click(screen.getByRole("tab", { name: "Brief" }))
    expect(screen.getByText("Reviewed account of the meeting.")).toBeVisible()
    expect(screen.getByRole("button", { name: "statement.pdf" })).toBeVisible()
  })

  it("records contact details on a narrow screen without changing the brief", async () => {
    await page.viewport(390, 844)
    const user = userEvent.setup()
    renderDossier()
    await user.click(
      await screen.findByRole("button", { name: "Add contacts" })
    )
    const dialog = screen.getByRole("dialog", {
      name: "Contact details for Witness Example",
    })
    await user.click(
      within(dialog).getByRole("button", { name: "Add contact" })
    )
    await user.type(within(dialog).getByLabelText("Label (optional)"), "Work")
    await user.type(within(dialog).getByLabelText("Value"), "+1 555 0100")
    expect(dialog.scrollWidth).toBeLessThanOrEqual(dialog.clientWidth)
    if (import.meta.env.VITE_DOSSIER_CAPTURE_DIR)
      await page.screenshot({
        path: `${import.meta.env.VITE_DOSSIER_CAPTURE_DIR}/dossier-contacts-mobile.png`,
      })
    await user.click(
      within(dialog).getByRole("button", { name: "Save contact details" })
    )
    expect(await screen.findByText("+1 555 0100")).toBeVisible()
    expect(dossier.summary).toBe("Investigator's own brief")
    expect(dossier.contacts?.[0].label).toBe("Work")
  })

  it("opens the existing dossier for a selected graph identity", async () => {
    const user = userEvent.setup()
    const onOpenExisting = vi.fn()
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })
    render(
      <QueryClientProvider client={client}>
        <DossierCreateSheet
          caseId="case-1"
          initialEntity={{ key: "person:current", name: "Current name" }}
          open
          onOpenChange={vi.fn()}
          onOpenExisting={onOpenExisting}
        />
      </QueryClientProvider>
    )
    await user.click(
      await screen.findByRole("button", { name: "Open existing dossier" })
    )
    expect(onOpenExisting).toHaveBeenCalledWith("dossier-1")
    expect(
      requests.some((request) =>
        request.url.includes("canonical_entity_key=person%3Acurrent")
      )
    ).toBe(true)
    expect(requests.some((request) => request.method === "POST")).toBe(false)
  })

  it("searches and pages through dossiers when attaching evidence", async () => {
    const user = userEvent.setup()
    listTotal = 101
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })
    render(
      <QueryClientProvider client={client}>
        <AddEvidenceToDossierDialog
          caseId="case-1"
          files={[{ id: "evidence-2", name: "new-statement.pdf" }]}
          open
          onOpenChange={vi.fn()}
        />
      </QueryClientProvider>
    )
    await user.click(
      await screen.findByRole("button", { name: "Next dossiers" })
    )
    await waitFor(() =>
      expect(
        requests.some((request) => request.url.includes("offset=50"))
      ).toBe(true)
    )
    await user.type(
      screen.getByPlaceholderText("Search Dossiers..."),
      "Witness"
    )
    await user.click(
      await screen.findByRole("option", { name: /Witness Example/ })
    )
    await user.click(screen.getByRole("button", { name: "Add to Dossier" }))
    await waitFor(() =>
      expect(
        dossier.links?.some((link) => link.target_id === "evidence-2")
      ).toBe(true)
    )
    expect(dossier.links?.some((link) => link.target_id === "entry-1")).toBe(
      true
    )
    expect(requests.some((request) => request.method === "PUT")).toBe(false)
  })
})


it("opens Workspace note sources and dossiers in overlays and returns to the same note", async () => {
  workspaceLinkJourney = true
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const user = userEvent.setup()
  render(<QueryClientProvider client={client}><MemoryRouter initialEntries={["/cases/case-1/workspace?view=casework&kind=note"]}><CaseworkListView caseId="case-1" entryType="note" canEdit /><LocationProbe /></MemoryRouter></QueryClientProvider>)
  await user.click(await screen.findByRole("heading", { name: "Witness follow-up" }))
  await user.click(await screen.findByRole("button", { name: /Original statement source/ }))
  expect(await screen.findByRole("img", { name: "Page 2 of the original PDF" })).toBeVisible()
  await user.keyboard("{Escape}")
  expect(screen.getByRole("heading", { name: "Witness follow-up" })).toBeVisible()
  await user.click(screen.getByRole("button", { name: /Witness dossier/ }))
  expect(await screen.findByRole("heading", { name: "Witness Example" })).toBeVisible()
  await user.keyboard("{Escape}")
  expect(screen.getByRole("heading", { name: "Witness follow-up" })).toBeVisible()
  expect(screen.getByLabelText("location")).toHaveTextContent("/cases/case-1/workspace?view=casework&kind=note")
})
