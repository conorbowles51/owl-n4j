import "@/styles/globals.css"
import { act, cleanup, render, screen, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { MemoryRouter } from "react-router-dom"
import { afterEach, expect, it, vi } from "vitest"
import { page } from "vitest/browser"
import { fetchAPI } from "@/lib/api-client"
import { AgentProposalsPanel } from "./AgentProposalsPanel"

vi.mock("@/lib/api-client", () => ({ fetchAPI: vi.fn() }))
afterEach(cleanup)

it("reviews one finding with its dossier and date, then reveals saved destinations after accepting", async () => {
  await page.viewport(1440, 950)
  let accepted = false
  const item = { id: "proposal-1", case_id: "synthetic-case", output_type: "entry_draft", review_status: "pending_review",
    content: { title: "Source-backed synthetic finding", body: "The record documents the agreed event date.", entry_type: "finding",
      dossier_name: "Synthetic witness", event_date: "2026-01-15", citations: ["doc://synthetic-source/1"] },
    citations: [{ cite: "doc://synthetic-source/1", label: "Synthetic source, page 1" }],
    proposal: { kind: "entry_draft", model: "Synthetic model" } }
  vi.mocked(fetchAPI).mockImplementation(async (url: string) => {
    if (url.includes("/glossary")) return { total: 0, items: [] }
    if (url.includes("/opened")) return { opened: ["doc://synthetic-source/1"] }
    if (url.includes("/accept")) {
      accepted = true
      return { ...item, review_status: "accepted", accepted_targets: [
        { target_type: "workspace_entry", target_id: "finding-1", href: "/cases/synthetic-case/workspace?view=casework&kind=finding&entry=finding-1", label: "Open saved finding" },
        { target_type: "dossier", target_id: "dossier-1", href: "/cases/synthetic-case/dossiers?dossier=dossier-1", label: "Open dossier" },
        { target_type: "timeline_entry", target_id: "event-1", href: "/cases/synthetic-case/timeline?event=timeline-entry:event-1", label: "Open dated event" },
      ] }
    }
    return { items: accepted ? [] : [item], total: accepted ? 0 : 1, returned: accepted ? 0 : 1, limit: 50, offset: 0 }
  })
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
    <MemoryRouter><div className="mx-auto max-w-4xl p-6"><AgentProposalsPanel caseId="synthetic-case" canEdit /></div></MemoryRouter>
  </QueryClientProvider>)
  expect(await screen.findByText("Attach to dossier: Synthetic witness.")).toBeVisible()
  expect(screen.getByText("Add dated timeline event: 2026-01-15.")).toBeVisible()
  expect(screen.getByTestId("proposal-accept")).toBeDisabled()
  await act(async () => { await page.getByTestId("proposal-open-source").click() })
  await screen.findByText("✓ opened")
  await act(async () => { await page.getByTestId("proposal-accept").click() })
  await waitFor(() => expect(screen.queryByTestId("agent-proposal")).toBeNull())
  expect(screen.getByLabelText("Saved proposal result")).toHaveFocus()
  expect(screen.getByRole("link", { name: "Open saved finding" })).toHaveAttribute("href", "/cases/synthetic-case/workspace?view=casework&kind=finding&entry=finding-1")
  expect(screen.getByRole("link", { name: "Open dossier" })).toBeVisible()
  expect(screen.getByRole("link", { name: "Open dated event" })).toBeVisible()
  expect(document.documentElement.scrollWidth).toBeLessThanOrEqual(1440)
})
