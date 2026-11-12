vi.mock("@/lib/api-client", () => ({ fetchAPI: vi.fn() }))
import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { MemoryRouter } from "react-router-dom"
import { expect, it, vi } from "vitest"
import { fetchAPI } from "@/lib/api-client"
import { AgentProposalsPanel } from "./AgentProposalsPanel"
import { alertAmount } from "../agent-proposals"

const lead = {
  id: "o-1",
  case_id: "case-a",
  output_type: "lead_card",
  review_status: "pending_review",
  created_at: "2026-11-03T10:00:00Z",
  content: {
    institution: "BBVA México",
    account_ending: "ending 4821",
    request_period: { start: "2024-01-15", end: "2024-03-02" },
    counts: { transactional: 2, account: 1 },
    alerts: [
      { cite: "rec://r-1", evidence_class: "transactional", at: "2024-01-15T09:30:00+00:00", amount_minor: 250000, currency: "MXN", direction: "credit" },
      { cite: "rec://r-2", evidence_class: "transactional", at: "2024-03-02T10:00:00+00:00", amount_minor: 150000, currency: "MXN", direction: "debit" },
    ],
    alerts_total: 2,
    citations: ["rec://r-1", "rec://r-2"],
  },
  citations: [
    { cite: "rec://r-1", label: "Phone record" },
    { cite: "rec://r-2", label: "Phone record" },
  ],
  proposal: { kind: "lead_card", model: "DeepSeek V4 Pro", for_name: "Verification user" },
}

it("a lead card lists each alert without a total, and is accepted only after a source is opened and a due date set", async () => {
  const api = vi.mocked(fetchAPI)
  api.mockImplementation(async (url: string) => {
    if (url.includes("/opened")) return { opened: ["rec://r-1"] }
    if (url.includes("/accept")) return { ...lead, review_status: "accepted" }
    return { items: [lead], total: 1, returned: 1, limit: 50, offset: 0 }
  })
  render(
    <QueryClientProvider client={new QueryClient()}>
      <AgentProposalsPanel caseId="case-a" canEdit />
    </QueryClientProvider>
  )
  expect(await screen.findByText(/BBVA México · ending 4821/)).toBeVisible()
  expect(screen.getByText(/2024-01-15 to 2024-03-02/)).toBeVisible()
  expect(screen.getByText(/MX\$2,500.00/)).toBeVisible()
  expect(screen.queryByText(/4,000/)).toBeNull()
  const accept = screen.getByTestId("proposal-accept")
  expect(accept).toBeDisabled()
  fireEvent.click(screen.getAllByTestId("proposal-open-source")[0])
  await screen.findByText("✓ opened")
  expect(accept).toBeDisabled() // no due date yet
  fireEvent.change(screen.getByLabelText("Task due"), { target: { value: "2026-11-10" } })
  expect(accept).toBeEnabled()
  fireEvent.click(accept)
  await waitFor(() =>
    expect(api).toHaveBeenCalledWith("/api/workspace/case-a/proposals/o-1/accept", {
      method: "POST",
      body: { due_at: "2026-11-10", via: "ui" },
    })
  )
})

it("formats an alert amount in its own currency's minor unit", () => {
  expect(alertAmount({ amount_minor: 1500, currency: "JPY" })).toBe("¥1,500")
  expect(alertAmount({ amount_minor: null, currency: "MXN" })).toBeNull()
})

const waiting = (over: Record<string, unknown>) => ({
  id: "o-9",
  case_id: "case-a",
  review_status: "pending_review",
  citations: [{ cite: "doc://1", label: "their-timeline.pdf", status: "valid" }],
  proposal: { kind: over.output_type, model: "DeepSeek V4 Pro", for_name: "Alex" },
  ...over,
})

function serve(items: unknown[], order_rule: string | null = null) {
  vi.mocked(fetchAPI).mockImplementation((url: string) => {
    if (url.includes("/glossary")) return Promise.resolve({ total: 0, confirmed: 0, items: [], limitation: "" }) as never
    return Promise.resolve({ items, total: items.length, returned: items.length, limit: 50, offset: 0, order_rule }) as never
  })
}

function panel() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <AgentProposalsPanel caseId="case-a" canEdit />
      </MemoryRouter>
    </QueryClientProvider>
  )
}

it("previews the complete finding action and keeps its saved destinations after the pending card disappears", async () => {
  const item = waiting({ output_type: "entry_draft", content: { title: "Synthetic finding", body: "Source-backed summary", entry_type: "finding", dossier_name: "Synthetic witness", event_date: "2026-01-15", citations: ["doc://1"] } })
  let accepted = false
  vi.mocked(fetchAPI).mockImplementation(async (url: string) => {
    if (url.includes("/glossary")) return { total: 0, items: [] }
    if (url.includes("/opened")) return { opened: ["doc://1"] }
    if (url.includes("/accept")) {
      accepted = true
      return { ...item, review_status: "accepted", accepted_targets: [
        { target_type: "workspace_entry", target_id: "e-1", label: "Open saved finding", href: "/cases/case-a/workspace?view=casework&kind=finding&entry=e-1" },
        { target_type: "dossier", target_id: "d-1", label: "Open dossier", href: "/cases/case-a/dossiers?dossier=d-1" },
        { target_type: "timeline_entry", target_id: "t-1", label: "Open dated event", href: "/cases/case-a/timeline?event=timeline-entry:t-1" },
      ] }
    }
    return { items: accepted ? [] : [item], total: accepted ? 0 : 1, returned: accepted ? 0 : 1, limit: 50, offset: 0 }
  })
  panel()
  expect(await screen.findByText("Attach to dossier: Synthetic witness.")).toBeVisible()
  expect(screen.getByText("Add dated timeline event: 2026-01-15.")).toBeVisible()
  fireEvent.click(screen.getByTestId("proposal-open-source"))
  await screen.findByText("✓ opened")
  fireEvent.click(screen.getByTestId("proposal-accept"))
  await waitFor(() => expect(screen.queryByTestId("agent-proposal")).toBeNull())
  expect(screen.getByRole("link", { name: "Open dossier" })).toHaveAttribute("href", "/cases/case-a/dossiers?dossier=d-1")
  expect(screen.getByRole("link", { name: "Open dated event" })).toBeVisible()
  expect(screen.getByLabelText("Saved proposal result")).toHaveFocus()
})

it("shows exactly which dossier fields and attachments the proposal will change", async () => {
  serve([waiting({ output_type: "dossier_change", content: { title: "Update dossier: Synthetic witness", operation: "update", why: "Requested correction", fields: { summary: "Revised description" }, before: { summary: "Original description" }, links: [{ target_type: "entry", target_id: "e-1", label: "Cited finding" }], citations: ["doc://1"] } })])
  panel()
  expect(await screen.findByTestId("dossier-proposal")).toHaveTextContent("Original description → Revised description")
  expect(screen.getByLabelText("Material to attach")).toHaveTextContent("Cited finding")
})

it("shows a lead card's draft schedule, labelled, and sends a person's edit", async () => {
  vi.mocked(fetchAPI).mockReset()
  serve([waiting({ output_type: "lead_card", content: { institution: "Synthetic Bank", schedule: "Institution: Synthetic Bank", schedule_label: "Drafted by the case agent, not confirmed. A person edits it; it is not a legal document.", citations: ["doc://1"] } })])
  panel()
  const box = await screen.findByLabelText("Draft production-order schedule")
  expect(screen.getByTestId("schedule-label").textContent).toContain("Drafted by the case agent, not confirmed")
  fireEvent.change(box, { target: { value: "Institution: Synthetic Bank, as edited" } })
  expect((box as HTMLTextAreaElement).value).toContain("as edited")
})

it("states why a kind sits where it does in the waiting list", async () => {
  vi.mocked(fetchAPI).mockReset()
  serve([waiting({ output_type: "statement_claim", order_reason: "Statement claim: 3 accepted of 4 decided in this case.", content: { kind: "no_contact", quote: "I never met him", window_text: "in March", citations: ["doc://1"] } })], "The rule.")
  panel()
  expect((await screen.findByTestId("proposal-order-reason")).textContent).toContain("3 accepted of 4 decided")
  expect(screen.getByTestId("proposal-order-rule").textContent).toBe("The rule.")
  expect(screen.getByTestId("claim-proposal").textContent).toContain("I never met him")
  expect(screen.getByTestId("claim-proposal").textContent).toContain("only a confirmed statement is checked")
})

it("keeps a code word's reading a model's until a person confirms it", async () => {
  vi.mocked(fetchAPI).mockReset()
  serve([waiting({ output_type: "glossary_term", content: { term: "breakfast", meaning: "a cash payment", citations: ["doc://1"] } })])
  panel()
  expect((await screen.findByTestId("term-proposal")).textContent).toContain("Model reading: a cash payment")
  expect((screen.getByLabelText("Meaning, in your words") as HTMLTextAreaElement).value).toBe("a cash payment")
  expect(screen.getByRole("button", { name: "Confirm this meaning" })).toBeDisabled()
})

it("says an entity was proposed by a model", async () => {
  vi.mocked(fetchAPI).mockReset()
  serve([waiting({ output_type: "entity_proposal", content: { name: "Pickup 7741", entity_type: "Document", summary: "A pickup code.", citations: ["doc://1"] } })])
  panel()
  expect((await screen.findByTestId("entity-proposal")).textContent).toContain("showing that a model proposed it")
})
