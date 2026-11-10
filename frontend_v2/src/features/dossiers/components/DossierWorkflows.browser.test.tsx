import {
  fireEvent,
  render,
  screen,
  within,
  waitFor,
} from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { MemoryRouter, useLocation } from "react-router-dom"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { page } from "vitest/browser"
import { CaseworkListView } from "@/features/workspace/components/CaseworkListView"
import { DossierDetailSheet } from "./DossierDetailSheet"
import { DossierCreateSheet } from "./DossierCreateSheet"
import { EditDossierDialog } from "./EditDossierDialog"
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
let interviewSaveGate: Promise<void> | null
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
  interviewSaveGate = null
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
    if (url.endsWith("/dossier-1/links:add") && method === "POST") {
      if (failSave) return json({ detail: "Temporary link failure" }, 503)
      const links = body.links as Array<{
        target_type: string
        target_id: string
        label: string
      }>
      for (const link of links)
        if (
          !dossier.links!.some(
            (existing) =>
              existing.target_type === link.target_type &&
              existing.target_id === link.target_id
          )
        )
          dossier.links!.push({
            id: `link-${link.target_id}`,
            ...link,
            source_anchor: {},
          })
      return json({
        added: links.length,
        skipped: 0,
        added_link_ids: links.map((link) => `link-${link.target_id}`),
        total_links: dossier.links!.length,
      })
    }
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
    if (/\/dossier-1\/links\/[^/]+$/.test(url) && method === "DELETE") {
      const id = url.split("/").pop()
      dossier.links = dossier.links!.filter((link) => link.id !== id)
      return json({ dossier_id: "dossier-1", removed: 1 })
    }
    if (url.endsWith("/interviews/interview-1") && method === "PATCH") {
      if (interviewSaveGate) await interviewSaveGate
      if (failSave)
        return json({ detail: "Temporary interview save failure" }, 503)
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
    if (url.includes("/api/phones/people/")) return json({ phones_in_case: 0 })
    if (url.includes("/entries/authors")) return json({ authors: [] })
    if (/\/entries\?/.test(url))
      return json({
        entries: [
          {
            id: "entry-2",
            entry_type: "finding",
            title: "Timestamp discrepancy",
            body: "Recorded times differ.",
            tags: [],
            links: [],
            review_state: "accepted",
            version: 1,
          },
          {
            id: "entry-1",
            entry_type: "note",
            title: "Witness follow-up",
            body: "Follow up on the recorded discrepancy.",
            tags: [],
            links: [],
            review_state: "accepted",
            version: 1,
          },
        ],
        total: 2,
      })
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
        links: workspaceLinkJourney
          ? [
              {
                id: "source",
                target_type: "evidence",
                target_id: "evidence-1",
                target_label: "Original statement source",
                relationship: "context",
                source_anchor: { page: 2 },
              },
              {
                id: "subject",
                target_type: "dossier",
                target_id: "dossier-1",
                target_label: "Witness dossier",
                relationship: "context",
                source_anchor: {},
              },
            ]
          : [],
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
function renderDossier(canEdit = true, onBeforeNavigate?: () => boolean) {
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
          onBeforeNavigate={onBeforeNavigate}
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

  it("opens casework that references the dossier and returns without copying the reference", async () => {
    const user = userEvent.setup()
    dossier.links = dossier.links!.filter(
      (link) => link.target_type !== "entry"
    )
    dossier.incoming_casework = [
      {
        id: "entry-1",
        title: "Witness follow-up",
        entry_type: "note",
        relationship: "context",
      },
    ]
    renderDossier()
    expect(await screen.findByText("Linked from casework")).toBeVisible()
    expect(
      screen.queryByRole("button", { name: "Unlink Witness follow-up" })
    ).not.toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: /Witness follow-up/ }))
    expect(
      await screen.findByText("Follow up on the recorded discrepancy.")
    ).toBeVisible()
    await user.keyboard("{Escape}")
    expect(screen.getByText("Linked from casework")).toBeVisible()
    expect(
      requests.some(
        (request) =>
          request.method === "POST" && request.url.endsWith("/links:add")
      )
    ).toBe(false)
  })

  it("protects an unsaved parent when a collected deadline leaves the dossier", async () => {
    const user = userEvent.setup()
    dossier.links!.push({
      id: "deadline-link",
      target_type: "deadline",
      target_id: "deadline-1",
      label: "Review due",
      source_anchor: {},
    })
    const allow = vi.fn().mockReturnValue(false)
    renderDossier(true, allow)
    await user.click(await screen.findByRole("button", { name: "Review due" }))
    expect(allow).toHaveBeenCalledTimes(1)
    expect(screen.getByLabelText("location")).toHaveTextContent(
      "/cases/case-1/dossiers?dossier=dossier-1"
    )
    allow.mockReturnValue(true)
    await user.click(screen.getByRole("button", { name: "Review due" }))
    expect(screen.getByLabelText("location")).toHaveTextContent(
      "/cases/case-1/workspace?view=work&item=deadline-1"
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

  it("collects existing casework, keeps failed selection, opens it and unlinks only the reference", async () => {
    const user = userEvent.setup()
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false)
    await page.viewport(1280, 900)
    renderDossier()
    await user.click(
      await screen.findByRole("button", { name: "Add casework" })
    )
    const picker = screen.getByRole("dialog", {
      name: "Add casework to Witness Example",
    })
    expect(
      await within(picker).findByRole("button", { name: /Witness follow-up/ })
    ).toBeDisabled()
    await user.click(
      within(picker).getByRole("button", { name: /Timestamp discrepancy/ })
    )
    await user.keyboard("{Escape}")
    expect(confirm).toHaveBeenCalledWith(
      "Discard your selected casework without linking it?"
    )
    expect(picker).toBeVisible()
    failSave = true
    await user.click(
      within(picker).getByRole("button", { name: "Link 1 item" })
    )
    expect(await within(picker).findByRole("alert")).toHaveTextContent(
      "Your selection is kept"
    )
    expect(
      within(picker).getByRole("button", { name: /Timestamp discrepancy/ })
    ).toHaveAttribute("aria-pressed", "true")
    failSave = false
    await user.click(
      within(picker).getByRole("button", { name: "Retry linking" })
    )
    await waitFor(() =>
      expect(
        screen.queryByRole("dialog", {
          name: "Add casework to Witness Example",
        })
      ).not.toBeInTheDocument()
    )
    expect(
      screen.getByRole("button", { name: "Timestamp discrepancy" })
    ).toBeVisible()
    expect(
      screen.getByRole("button", { name: "Witness follow-up" })
    ).toBeVisible()
    expect(
      requests.some(
        (request) => request.method === "PUT" && request.url.endsWith("/links")
      )
    ).toBe(false)
    await user.click(
      screen.getByRole("button", { name: "Unlink Timestamp discrepancy" })
    )
    await user.click(
      within(
        screen.getByRole("dialog", { name: "Unlink this item?" })
      ).getByRole("button", { name: "Unlink" })
    )
    await waitFor(() =>
      expect(
        screen.queryByRole("button", { name: "Timestamp discrepancy" })
      ).not.toBeInTheDocument()
    )
    expect(dossier.links!.some((link) => link.target_id === "entry-1")).toBe(
      true
    )
    expect(
      requests
        .filter((request) => request.method === "DELETE")
        .map((request) => request.url)
    ).toEqual(["/api/dossiers/dossier-1/links/link-entry-2"])
  })

  it("unlinks a phone message from the dossier through its link, leaving the other links", async () => {
    dossier.links!.push({
      id: "phone-link",
      target_type: "phone_record",
      target_id: "record-1",
      label: "Synthetic sender -> Owner of C1",
      source_anchor: {},
    })
    const user = userEvent.setup()
    renderDossier()
    await user.click(
      await screen.findByRole("button", {
        name: "Unlink Synthetic sender -> Owner of C1",
      })
    )
    const confirm = screen.getByRole("dialog", { name: "Unlink this item?" })
    expect(confirm).toHaveTextContent(
      "The item itself and other dossier links stay unchanged."
    )
    await user.click(within(confirm).getByRole("button", { name: "Unlink" }))
    await waitFor(() =>
      expect(
        screen.queryByText("Synthetic sender -> Owner of C1")
      ).not.toBeInTheDocument()
    )
    expect(
      requests.filter((r) => r.method === "DELETE").map((r) => r.url)
    ).toEqual(["/api/dossiers/dossier-1/links/phone-link"])
    expect(
      screen.getAllByRole("button", { name: "statement.pdf" })[0]
    ).toBeVisible()
    expect(
      screen.getByRole("button", { name: "Witness follow-up" })
    ).toBeVisible()
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
    expect(
      await screen.findByText(/Your brief could not be saved/)
    ).toHaveTextContent("Your writing is kept")
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

  it("retains an interview draft after cancelled closes and failed saves, then reopens the saved changes", async () => {
    const user = userEvent.setup()
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false)
    renderDossier()
    await user.click(await screen.findByRole("tab", { name: "Interviews" }))
    await user.click(screen.getByRole("button", { name: /Edit interview/ }))
    const dialog = screen.getByRole("dialog", {
      name: "Edit interview or statement",
    })
    const notes = within(dialog).getByLabelText("Working notes")
    await user.clear(notes)
    await user.type(
      notes,
      "Witness clarified the meeting time; verify against the original statement."
    )
    await user.type(
      within(dialog).getByLabelText("Participants"),
      ", Investigator Example"
    )
    await user.type(
      within(dialog).getByLabelText("Interviewed by"),
      "Case investigator"
    )
    fireEvent.change(within(dialog).getByLabelText("Month and year"), {
      target: { value: "2025-08" },
    })

    await user.click(within(dialog).getByRole("button", { name: "Cancel" }))
    await user.keyboard("{Escape}")
    expect(confirm).toHaveBeenCalledTimes(2)
    expect(notes).toHaveValue(
      "Witness clarified the meeting time; verify against the original statement."
    )
    expect(within(dialog).getByLabelText("Participants")).toHaveValue(
      "Witness Example, Investigator Example"
    )
    expect(within(dialog).getByLabelText("Month and year")).toHaveValue(
      "2025-08"
    )
    expect(requests.some((request) => request.method === "PATCH")).toBe(false)

    failSave = true
    await user.click(
      within(dialog).getByRole("button", { name: "Save interview" })
    )
    expect(await within(dialog).findByRole("alert")).toHaveTextContent(
      "Temporary interview save failure"
    )
    expect(notes).toHaveValue(
      "Witness clarified the meeting time; verify against the original statement."
    )
    failSave = false
    let finishSave!: () => void
    interviewSaveGate = new Promise<void>((resolve) => {
      finishSave = resolve
    })
    await user.click(
      within(dialog).getByRole("button", { name: "Save interview" })
    )
    expect(
      within(dialog).getByRole("button", { name: "Saving…" })
    ).toBeDisabled()
    expect(within(dialog).getByRole("button", { name: "Add" })).toBeDisabled()
    await user.keyboard("{Escape}")
    expect(dialog).toBeVisible()
    expect(confirm).toHaveBeenCalledTimes(2)
    finishSave()
    await waitFor(() =>
      expect(
        screen.queryByRole("dialog", { name: "Edit interview or statement" })
      ).not.toBeInTheDocument()
    )

    await user.click(screen.getByRole("button", { name: /Edit interview/ }))
    const reopened = screen.getByRole("dialog", {
      name: "Edit interview or statement",
    })
    expect(within(reopened).getByLabelText("Working notes")).toHaveValue(
      "Witness clarified the meeting time; verify against the original statement."
    )
    expect(within(reopened).getByLabelText("Participants")).toHaveValue(
      "Witness Example, Investigator Example"
    )
    expect(within(reopened).getByLabelText("Interviewed by")).toHaveValue(
      "Case investigator"
    )
    expect(within(reopened).getByLabelText("Month and year")).toHaveValue(
      "2025-08"
    )
    await user.click(within(reopened).getByRole("button", { name: "Cancel" }))
    expect(confirm).toHaveBeenCalledTimes(2)
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

  it("protects new dossier writing before closing or opening an existing subject", async () => {
    const user = userEvent.setup()
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false)
    const onOpenChange = vi.fn()
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
          onOpenChange={onOpenChange}
          onOpenExisting={onOpenExisting}
        />
      </QueryClientProvider>
    )
    await user.type(
      screen.getByLabelText("Investigator summary"),
      "Unsaved source context"
    )
    await user.click(screen.getByRole("button", { name: "Cancel" }))
    await user.click(
      await screen.findByRole("button", { name: "Open existing dossier" })
    )
    expect(onOpenChange).not.toHaveBeenCalled()
    expect(onOpenExisting).not.toHaveBeenCalled()
    expect(screen.getByLabelText("Investigator summary")).toHaveValue(
      "Unsaved source context"
    )
    confirm.mockReturnValue(true)
    await user.click(screen.getByRole("button", { name: "Cancel" }))
    expect(onOpenChange).toHaveBeenCalledWith(false)
  })

  it("retains dossier details after a cancelled close and failed save", async () => {
    const user = userEvent.setup()
    vi.spyOn(window, "confirm").mockReturnValue(false)
    const onClose = vi.fn()
    const client = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    })
    render(
      <QueryClientProvider client={client}>
        <EditDossierDialog dossier={dossier} onClose={onClose} />
      </QueryClientProvider>
    )
    await user.type(
      screen.getByLabelText("Why this subject matters"),
      "Can confirm the meeting time"
    )
    await user.click(screen.getByRole("button", { name: "Cancel" }))
    expect(onClose).not.toHaveBeenCalled()
    failSave = true
    await user.click(
      screen.getByRole("button", { name: "Save dossier details" })
    )
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Your changes are kept"
    )
    expect(screen.getByLabelText("Why this subject matters")).toHaveValue(
      "Can confirm the meeting time"
    )
    failSave = false
    await user.click(
      screen.getByRole("button", { name: "Save dossier details" })
    )
    await waitFor(() => expect(onClose).toHaveBeenCalledOnce())
    expect(dossier.importance).toBe("Can confirm the meeting time")
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
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  const user = userEvent.setup()
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter
        initialEntries={["/cases/case-1/workspace?view=casework&kind=note"]}
      >
        <CaseworkListView caseId="case-1" entryType="note" canEdit />
        <LocationProbe />
      </MemoryRouter>
    </QueryClientProvider>
  )
  await user.click(
    await screen.findByRole("button", { name: /Witness follow-up/ })
  )
  await user.click(
    await screen.findByRole("button", { name: /Original statement source/ })
  )
  expect(
    await screen.findByRole("img", { name: "Page 2 of the original PDF" })
  ).toBeVisible()
  await user.keyboard("{Escape}")
  expect(
    screen.getByRole("heading", { name: "Witness follow-up" })
  ).toBeVisible()
  await user.click(screen.getByRole("button", { name: /Witness dossier/ }))
  expect(
    await screen.findByRole("heading", { name: "Witness Example" })
  ).toBeVisible()
  await user.keyboard("{Escape}")
  expect(
    screen.getByRole("heading", { name: "Witness follow-up" })
  ).toBeVisible()
  expect(screen.getByLabelText("location")).toHaveTextContent(
    "/cases/case-1/workspace?view=casework&kind=note"
  )
})
