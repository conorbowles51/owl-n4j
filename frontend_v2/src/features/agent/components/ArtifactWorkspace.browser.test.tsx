import "@/styles/globals.css"
import { useState } from "react"
import { act, cleanup, render, screen, waitFor, within } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { page } from "vitest/browser"
import { afterEach, expect, it, vi } from "vitest"
import { ArtifactWorkspace } from "./AgentPage"
import { ExtendedArtifact } from "./ExtendedArtifact"
import { agentAPI } from "../api"
import type { AgentArtifact } from "../types"

vi.mock("../api", () => ({ agentAPI: { artifactVersions: vi.fn(), reviseArtifact: vi.fn(), getArtifact: vi.fn(), artifactExportUrl: () => "/synthetic-export" } }))
afterEach(cleanup)

it("shows source review failures on reopening and offers to repair the same saved report", async () => {
  const resolve = vi.fn()
  const draft: AgentArtifact = { id: "review-draft", type: "report", title: "Synthetic source review", metadata: {
    revision: 4, validation: { status: "structural_checks_passed", issues: [] },
    completion_review: { status: "needs_revision", issues: ["The stated sequence contradicts its cited source."] },
  }, data: { sections: [{ id: "analysis", heading: "Analysis", content: "Saved draft content." }] } }
  vi.mocked(agentAPI.artifactVersions).mockResolvedValue([draft])
  render(<MemoryRouter><div className="h-screen"><ArtifactWorkspace artifacts={[draft]} selectedArtifact={draft} selectedArtifactId={draft.id}
    onSelectArtifact={() => {}} exportEnabled onEntitySelect={() => {}} onSaved={() => {}} onRevise={resolve} /></div></MemoryRouter>)
  expect(screen.getByText("The stated sequence contradicts its cited source.")).toBeVisible()
  await page.getByRole("button", { name: "Resolve checks with agent" }).click()
  expect(resolve).toHaveBeenCalledWith(expect.stringContaining("saved artifact review-draft (version 4)"))
})

it("keeps authored record lines visually separate in the report viewer", async () => {
  await page.viewport(1440, 950)
  const records: AgentArtifact = { id: "record-lines", type: "report", title: "Synthetic register", metadata: {}, data: {
    sections: [{ id: "records", heading: "Source records", content: "**RECORD-A** First observation.\n**RECORD-B** Second observation." }],
  } }
  vi.mocked(agentAPI.artifactVersions).mockResolvedValue([records])
  render(<MemoryRouter><div className="h-screen"><ArtifactWorkspace artifacts={[records]} selectedArtifact={records} selectedArtifactId={records.id}
    onSelectArtifact={() => {}} exportEnabled onEntitySelect={() => {}} onSaved={() => {}} onRevise={() => {}} /></div></MemoryRouter>)
  const first = screen.getByText("RECORD-A")
  const second = screen.getByText("RECORD-B")
  expect(second.getBoundingClientRect().y).toBeGreaterThan(first.getBoundingClientRect().y + 5)
})

it("shows all nearby synthetic map locations separately and preserves their assumption note", async () => {
  await page.viewport(1440, 950)
  const map: AgentArtifact = { id: "map-points", type: "map", title: "Synthetic meetings", metadata: { revision: 1 }, data: {
    note: "Illustrative assumptions only; these are not observed meetings.",
    points: [{ label: "Meeting A", lat: 53.3, lng: -6.2 }, { label: "Meeting B", lat: 53.4, lng: -6.3 }, { label: "Meeting C", lat: 53.5, lng: -6.4 }],
  } }
  vi.mocked(agentAPI.artifactVersions).mockResolvedValue([map])
  render(<MemoryRouter><div className="h-screen"><ArtifactWorkspace artifacts={[map]} selectedArtifact={map} selectedArtifactId={map.id}
    onSelectArtifact={() => {}} exportEnabled onEntitySelect={() => {}} onSaved={() => {}} onRevise={() => {}} /></div></MemoryRouter>)
  const first = screen.getByRole("button", { name: "Location 1: Meeting A" })
  const last = screen.getByRole("button", { name: "Location 3: Meeting C" })
  expect(first).toBeVisible()
  expect(last).toBeVisible()
  expect(Math.abs(first.getBoundingClientRect().x - last.getBoundingClientRect().x)).toBeGreaterThan(100)
  expect(screen.getByText("Illustrative assumptions only; these are not observed meetings.")).toBeVisible()
  expect(screen.getByText("53.4, -6.3")).toBeVisible()
})

const report: AgentArtifact = {
  id: "first-report", type: "report", title: "Synthetic investigation report", metadata: { deliverable_id: "report-family", revision: 1 },
  data: { purpose: "Complete examination of the synthetic case.", scope: "Synthetic evidence only; no client records.", sources: [{ label: "Synthetic reference", url: "https://example.com/synthetic", locator: "Page 14" }], sections: Array.from({ length: 30 }, (_, i) => ({
    id: `s${i}`, heading: `Subject ${i + 1}`, content: `Original content for subject ${i + 1}.`,
    embeds: i === 29 ? [{ type: "table", title: "Complete exhibit", data: {
      columns: Array.from({ length: 10 }, (_, c) => ({ key: `c${c}`, label: `Column ${c + 1}` })),
      rows: Array.from({ length: 1500 }, (_, r) => Object.fromEntries(Array.from({ length: 10 }, (_, c) => [`c${c}`, `Row ${r + 1}, value ${c + 1}`]))),
    } }] : [],
    children: i === 29 ? [{ id: "nested", heading: "Nested supporting analysis", content: "Complete nested section content." }] : [],
  })) },
}
function Fixture() {
  const [artifacts, setArtifacts] = useState<AgentArtifact[]>([report, ...Array.from({ length: 11 }, (_, i): AgentArtifact => ({
    id: `later-${i}`, title: `Later exhibit ${i + 1}`, type: "matrix", metadata: {}, data: { rows: [{ label: `Exhibit ${i + 1}` }] },
  }))])
  const [selected, setSelected] = useState(artifacts[11])
  return <MemoryRouter><div className="h-screen"><ArtifactWorkspace artifacts={artifacts} selectedArtifact={selected} selectedArtifactId={selected.id} onSelectArtifact={setSelected} exportEnabled onEntitySelect={() => {}} onSaved={(next) => { setArtifacts((a) => [...a, next]); setSelected(next) }} onRevise={() => {}} /></div></MemoryRouter>
}

it("retrieves the earliest of twelve artifacts, reads all report sections and full table data, and saves a preserving revision", async () => {
  await page.viewport(1440, 950)
  vi.mocked(agentAPI.artifactVersions).mockResolvedValue([report])
  vi.mocked(agentAPI.reviseArtifact).mockImplementation(async (_id, body) => ({ ...report, id: "report-v2", title: body.title || report.title, data: body.data, metadata: { deliverable_id: "report-family", revision: 2 } }))
  render(<Fixture />)
  await page.getByRole("textbox", { name: "Search saved artifacts" }).fill("Synthetic investigation")
  await page.getByRole("button", { name: /Synthetic investigation report v1/ }).click()
  expect(screen.getByText("12 saved deliverables · 12 versions")).toBeVisible()
  await page.screenshot({ path: "../../../../../output/playwright/agent-report-workspace-desktop.png" })
  await page.getByRole("link", { name: "30 Subject 30", exact: true }).click()
  expect(screen.getByRole("heading", { name: "Subject 30" })).toBeVisible()
  expect(screen.getByRole("heading", { level: 3, name: "Nested supporting analysis" })).toBeInTheDocument()
  expect(screen.getByRole("link", { name: "Synthetic reference" })).toHaveAttribute("href", "https://example.com/synthetic")
  const table = screen.getByRole("region", { name: "Complete exhibit" })
  expect(within(table).getByRole("button", { name: "Sort by Column 10" })).toBeInTheDocument()
  await page.getByRole("button", { name: "Last", exact: true }).click()
  expect(screen.getByText("Row 1500, value 10")).toBeInTheDocument()
  await page.getByRole("textbox", { name: "Search Complete exhibit" }).fill("Row 1200,")
  expect(screen.getByText("Row 1200, value 10")).toBeInTheDocument()
  await page.getByRole("textbox", { name: "Search Complete exhibit" }).fill("")
  await page.getByRole("button", { name: "Sort by Column 1", exact: true }).click()
  await page.getByRole("button", { name: "Sort by Column 1", exact: true }).click()
  expect(within(table).getAllByRole("row")[1]).toHaveTextContent("Row 1500, value 1")
  await page.getByRole("button", { name: "Edit or revise" }).click()
  await act(async () => { screen.getAllByText("Subject 1", { exact: true }).find((el) => el.tagName === "SUMMARY")?.click() })
  await page.getByRole("textbox", { name: "Section 1 content", exact: true }).fill("Investigator correction retained.")
  await page.getByRole("button", { name: "Save new version" }).click()
  await waitFor(() => expect(screen.getByText("12 saved deliverables · 13 versions")).toBeVisible())
  const saved = vi.mocked(agentAPI.reviseArtifact).mock.calls[0][1]
  expect(saved.expected_revision).toBe(1)
  const sections = saved.data.sections as { content: string; embeds: unknown[] }[]
  expect(sections).toHaveLength(30)
  expect(sections[0].content).toBe("Investigator correction retained.")
  expect(sections[29].embeds).toEqual((report.data.sections as { embeds: unknown[] }[])[29].embeds)
  await page.getByRole("combobox", { name: "Artifact version" }).selectOptions("first-report")
  expect(screen.getByText("Original content for subject 1.")).toBeInTheDocument()
})

it("retains unsaved edits on a revision conflict and keeps mobile navigation usable", async () => {
  await page.viewport(390, 844)
  vi.mocked(agentAPI.reviseArtifact).mockRejectedValue(new Error("This artifact has a newer revision."))
  render(<Fixture />)
  await page.getByRole("textbox", { name: "Search saved artifacts" }).fill("Synthetic")
  await page.getByRole("button", { name: /Synthetic investigation report v1/ }).click()
  await page.getByRole("button", { name: "Edit or revise" }).click()
  await page.getByRole("textbox", { name: "Title", exact: true }).fill("My unsaved title")
  await page.getByRole("button", { name: "Save new version" }).click()
  await screen.findByRole("alert")
  expect(screen.getByRole("textbox", { name: "Title" })).toHaveValue("My unsaved title")
  expect(screen.getByRole("alert")).toHaveTextContent("Your edits are still here")
  expect(document.documentElement.scrollWidth).toBeLessThanOrEqual(390)
  await page.screenshot({ path: "../../../../../output/playwright/agent-report-workspace-mobile.png" })
})

it("isolates custom interactive content from application origin and network while retaining a readable alternative", async () => {
  await page.viewport(1440, 950)
  render(<ExtendedArtifact artifact={{ id: "interactive", type: "interactive", title: "Synthetic calculator", metadata: {}, data: {
    html: '<meta http-equiv="refresh" content="0;url=https://example.com/leak"><input id="n" type="number" value="4" onchange="location=\'https://example.com/leak\'"><output id="result">8</output><script>n.oninput=()=>result.textContent=Number(n.value)*2</script><a href="https://example.com/leak" ping="https://example.com/leak">Unsafe link</a>',
    interactions: { inputs: [{ key: "amount", label: "Assumed amount", value: 4 }], calculations: [{ key: "double", label: "Doubled amount", expression: "amount * 2" }] },
    static_content: "At the saved assumption of 4, the result is 8.",
  } }} />)
  const iframe = screen.getByTitle("Synthetic calculator")
  expect(iframe).toHaveAttribute("sandbox", "")
  expect(iframe).toHaveAttribute("referrerpolicy", "no-referrer")
  expect(iframe.getAttribute("srcdoc")).toContain("connect-src 'none'")
  expect(iframe.getAttribute("srcdoc")).toContain("default-src 'none'")
  expect(iframe.getAttribute("srcdoc")).toContain("script-src 'none'")
  expect(iframe.getAttribute("srcdoc")).not.toContain("example.com")
  expect(iframe.getAttribute("srcdoc")).not.toContain("<script")
  await page.getByRole("spinbutton", { name: "Assumed amount" }).fill("9")
  expect(screen.getByText("18", { exact: true })).toBeVisible()
  await page.getByText("Readable alternative", { exact: true }).click()
  expect(screen.getByText("At the saved assumption of 4, the result is 8.")).toBeVisible()
})

function FormatsFixture() {
  const artifacts: AgentArtifact[] = [
    { id: "workbook", type: "workbook", title: "Synthetic workbook", metadata: {}, data: { sheets: [
      { name: "Summary", rows: [{ total: 23 }], formulas: [{ cell: "A2", formula: "SUM(Details!A2:A24)" }] },
      { name: "Details", rows: Array.from({ length: 120 }, (_, i) => ({ record: `Workbook source ${i + 1}` })) },
    ] } },
    { id: "deck", type: "presentation", title: "Synthetic presentation", metadata: {}, data: { slides: Array.from({ length: 26 }, (_, i) => ({ title: `Slide ${i + 1}`, content: `Briefing content ${i + 1}`, notes: `Speaker note ${i + 1}`, embeds: i === 25 ? [{ type: "table", title: "Final slide exhibit", data: { rows: [{ source: "All final exhibit data" }] } }] : [] })) } },
    { id: "diagram", type: "diagram", title: "Synthetic process", metadata: {}, data: { nodes: [{ id: "start", label: "Full name of the starting process stage" }, { id: "finish", label: "Finished" }], links: [{ source: "start", target: "finish", type: "next" }] } },
    { id: "map", type: "map", title: "Synthetic locations", metadata: {}, data: { locations: Array.from({ length: 30 }, (_, i) => ({ name: `Place ${i + 1}`, latitude: i, longitude: i })) } },
  ]
  const [selected, setSelected] = useState(artifacts[0])
  return <MemoryRouter><div className="h-screen"><ArtifactWorkspace artifacts={artifacts} selectedArtifact={selected} selectedArtifactId={selected.id} onSelectArtifact={setSelected} onSaved={setSelected} onRevise={() => {}} exportEnabled onEntitySelect={() => {}} /></div></MemoryRouter>
}

it("opens every workbook sheet, complete slide exhibits, diagram data and all map locations", async () => {
  await page.viewport(1440, 950)
  render(<FormatsFixture />)
  await page.getByRole("tab", { name: "Details", exact: true }).click()
  await page.getByRole("button", { name: "Last", exact: true }).click()
  expect(screen.getByText("Workbook source 120")).toBeInTheDocument()
  await page.getByRole("button", { name: /Synthetic presentation v1/ }).click()
  expect(screen.getByRole("heading", { name: "Slide 26" })).toBeInTheDocument()
  expect(screen.getByText("All final exhibit data")).toBeInTheDocument()
  expect(screen.getAllByText("Speaker notes")).toHaveLength(26)
  await page.getByRole("button", { name: /Synthetic process v1/ }).click()
  expect(screen.queryByRole("button", { name: "Spotlight" })).not.toBeInTheDocument()
  await page.getByText("All nodes and relationships", { exact: true }).click()
  expect(screen.getByText("Full name of the starting process stage")).toBeVisible()
  expect(screen.getByText("next", { exact: true })).toBeVisible()
  await page.getByRole("button", { name: /Synthetic locations v1/ }).click()
  expect(screen.getByRole("button", { name: "Place 30 29, 29" })).toBeInTheDocument()
})

const previousReview: AgentArtifact = { id: "review-v1", title: "Initial review report", type: "report", metadata: { deliverable_id: "review-family", revision: 1 }, data: { sections: [{ id: "summary", heading: "Summary", content: "Same summary", children: [{ id: "analysis", heading: "Analysis", content: "Earlier analysis text." }, { id: "removed", heading: "Removed appendix", content: "Old appendix." }], embeds: [{ artifact_id: "source-v1", title: "Supporting records", type: "table", data: { columns: ["record"], rows: [{ record: "A" }] } }] }] } }
const currentReview: AgentArtifact = { ...previousReview, id: "review-v2", title: "Revised review report", metadata: { deliverable_id: "review-family", revision: 2, previous_revision_id: previousReview.id, dependency_review: { status: "review_needed", items: [{ artifact_id: "source-v2", title: "Supporting records", location: "data.sections.0.embeds.0", pinned_revision: 2, latest_revision: 3, latest_artifact_id: "source-v3", status: "newer_revision_available" }] } }, data: { sections: [{ id: "summary", heading: "Summary", content: "Same summary", children: [{ id: "analysis", heading: "Expanded analysis", content: "Revised analysis text." }, { id: "added", heading: "Added limitations", content: "New limitations." }], embeds: [{ artifact_id: "source-v2", title: "Supporting records", type: "table", data: { columns: ["record", "note"], rows: [{ record: "A", note: "Reviewed" }, { record: "B", note: "Reviewed" }] } }] }] } }
function ReviewFixture({ initial = currentReview }: { initial?: AgentArtifact }) {
  const [artifacts, setArtifacts] = useState([initial])
  const [selected, setSelected] = useState(initial)
  return <MemoryRouter><div className="h-screen"><ArtifactWorkspace artifacts={artifacts} selectedArtifact={selected} selectedArtifactId={selected.id} onSelectArtifact={setSelected} onSaved={(artifact) => { setArtifacts((current) => [...current.filter((a) => a.id !== artifact.id), artifact]); setSelected(artifact) }} onRevise={() => {}} exportEnabled onEntitySelect={() => {}} /></div></MemoryRouter>
}

it("compares nested report revisions, reviews newer source data and records a reason to retain the pinned exhibit", async () => {
  await page.viewport(1440, 950)
  vi.mocked(agentAPI.artifactVersions).mockResolvedValue([previousReview, currentReview])
  vi.mocked(agentAPI.getArtifact).mockResolvedValue({ id: "source-v3", title: "Supporting records", type: "table", metadata: { revision: 3 }, data: { rows: [{ record: "A" }, { record: "B" }, { record: "New source row" }] } })
  vi.mocked(agentAPI.reviseArtifact).mockImplementation(async (_id, body) => ({ ...currentReview, id: "review-v3", data: body.data, metadata: { deliverable_id: "review-family", revision: 3 } }))
  render(<ReviewFixture />)
  await page.getByRole("button", { name: "Compare with previous" }).click()
  const comparison = screen.getByRole("region", { name: "Version comparison" })
  await waitFor(() => expect(comparison).toHaveFocus())
  expect(within(comparison).getByText("Version 1 → Version 2")).toBeVisible()
  expect(within(comparison).getByText("1 added · 1 removed · 2 changed sections")).toBeVisible()
  await page.getByText("ChangedExpanded analysis", { exact: true }).click()
  expect(within(comparison).getByText("Earlier analysis text.")).toBeVisible()
  expect(within(comparison).getByText("Revised analysis text.")).toBeVisible()
  expect(within(comparison).getByText("Rows: 1 → 2 · Columns: 1 → 2")).toBeInTheDocument()
  expect(within(comparison).getByText(/Before columns:/).closest("p")).toHaveTextContent("record")
  expect(within(comparison).getByText(/After columns:/).closest("p")).toHaveTextContent("record, note")
  await page.getByRole("button", { name: "Close comparison" }).click()
  await page.getByRole("button", { name: "Review newer version" }).click()
  expect(await screen.findByText("New source row")).toBeVisible()
  await page.getByRole("button", { name: "Revised review report v2", exact: true }).click()
  await page.getByText("Keep the pinned version after review", { exact: true }).click()
  await page.getByRole("textbox", { name: "Reason for keeping Supporting records" }).fill("The report describes the original reviewed period; the newer source is outside its scope.")
  await page.getByRole("button", { name: "Save review in new version" }).click()
  await screen.findByRole("button", { name: "Revised review report v3" })
  const body = vi.mocked(agentAPI.reviseArtifact).mock.calls.at(-1)![1]
  expect(body.expected_revision).toBe(2)
  const section = (body.data.sections as Record<string, unknown>[])[0]
  const embed = (section.embeds as Record<string, unknown>[])[0]
  expect(embed.artifact_id).toBe("source-v2")
  expect(embed.dependency_review).toMatchObject({ decision: "retain_pinned", latest_artifact_id: "source-v3", reason: expect.stringContaining("original reviewed period") })
  expect((embed.data as { rows: unknown[] }).rows).toHaveLength(2)
})

it("retains a copied workbook population only after recording why its newer source is not adopted", async () => {
  await page.viewport(1440, 950)
  const source = "00000000-0000-0000-0000-000000000099"
  const workbook: AgentArtifact = { id: "copied-workbook", type: "workbook", title: "Saved analysis", data: { sheets: [{ name: "Data", rows: [{ amount: 2 }] }] },
    metadata: { revision: 1, dependency_review: { status: "review_needed", items: [{ artifact_id: source, title: "Source population", dependency_kind: "copied_input",
      location: `data.source_dependency_reviews.${source}`, pinned_revision: 1, latest_revision: 2, latest_artifact_id: "newer-source", status: "newer_revision_available" }] } } }
  vi.mocked(agentAPI.reviseArtifact).mockImplementation(async (_id, body) => ({ ...workbook, id: "copied-workbook-v2", data: body.data, metadata: { deliverable_id: workbook.id, revision: 2 } }))
  render(<ReviewFixture initial={workbook} />)
  expect(screen.getByText("Linked artifacts have newer versions")).toBeVisible()
  await page.getByText("Keep the pinned version after review", { exact: true }).click()
  await page.getByRole("textbox", { name: "Reason for keeping Source population" }).fill("Retain the original population for this dated comparison.")
  await page.getByRole("button", { name: "Save review in new version" }).click()
  await screen.findByRole("button", { name: "Saved analysis v2" })
  const body = vi.mocked(agentAPI.reviseArtifact).mock.calls.at(-1)![1]
  expect(body.data.sheets).toEqual(workbook.data.sheets)
  expect(body.data.source_dependency_reviews).toEqual({ [source]: { artifact_id: source,
    dependency_review: { decision: "retain_pinned", latest_artifact_id: "newer-source", reason: "Retain the original population for this dated comparison." } } })
})
