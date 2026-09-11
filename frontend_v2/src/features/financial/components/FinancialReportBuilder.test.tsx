import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { beforeEach, expect, it, vi } from "vitest"
import { savedIndirectFixture } from "@/test/indirect-workpaper-fixture"
import { useFinancialDraftStore } from "../stores/financial-drafts"
import { reportDraftName } from "../lib/financial-report"
import { FinancialReportBuilder } from "./FinancialReportBuilder"

const api = vi.hoisted(() => ({ get: vi.fn(), create: vi.fn() }))
vi.mock("@/features/workspace/casework-api", () => ({ caseworkAPI: api }))
beforeEach(() => {
  api.get.mockReset()
  api.create.mockReset()
  useFinancialDraftStore.setState({ drafts: {} })
})
async function setup() {
  const f = await savedIndirectFixture()
  const key = `anonymous:${f.caseId}:${reportDraftName}`
  useFinancialDraftStore
    .getState()
    .put(key, {
      title: "Comparison for review",
      introduction: "Check these records",
      selected: [{ id: f.entry.id, title: f.entry.title, version: 1 }],
    })
  api.get.mockResolvedValue(f.entry)
  api.create.mockResolvedValue({ ...f.entry, id: "report-created" })
  render(
    <QueryClientProvider
      client={
        new QueryClient({
          defaultOptions: {
            queries: { retry: false },
            mutations: { retry: false },
          },
        })
      }
    >
      <FinancialReportBuilder caseId={f.caseId} caseTitle="Synthetic case" />
    </QueryClientProvider>
  )
  fireEvent.click(screen.getByRole("button", { name: "Build report (1)" }))
  return { ...f, key }
}
async function preview() {
  fireEvent.click(screen.getByRole("button", { name: "Preview report" }))
  await screen.findByTitle("Financial report preview")
}
it("retains the draft on closing, invalidates an edited preview, and saves exactly the previewed note version", async () => {
  const f = await setup()
  await preview()
  expect(
    screen.getByLabelText("Include the supporting PDFs in the download package")
  ).not.toBeChecked()
  fireEvent.change(screen.getByLabelText("Report title"), {
    target: { value: "Updated report title" },
  })
  expect(screen.queryByTitle("Financial report preview")).toBeNull()
  fireEvent.click(screen.getByRole("button", { name: "Close report builder" }))
  fireEvent.click(screen.getByRole("button", { name: "Build report (1)" }))
  expect(screen.getByLabelText("Report title")).toHaveValue(
    "Updated report title"
  )
  await preview()
  api.get.mockResolvedValue({
    ...f.entry,
    version: 2,
    body: "Edited after preview",
  })
  fireEvent.click(screen.getByRole("button", { name: "Save report to case" }))
  await screen.findByText(/Report saved to this case/)
  expect(api.create).toHaveBeenCalledTimes(1)
  const sent = api.create.mock.calls[0][1]
  expect(sent.title).toBe("Updated report title")
  const data = JSON.parse(sent.links[0].metadata.envelope.report_json)
  expect(data.notes[0].version).toBe(1)
  expect(data.notes[0].body).toBe(f.entry.body)
  expect(useFinancialDraftStore.getState().drafts[f.key]).toMatchObject({
    selected: [],
  })
})
it("requires an explicit update when a note changed since selection", async () => {
  const f = await setup()
  api.get.mockResolvedValue({ ...f.entry, version: 2 })
  fireEvent.click(screen.getByRole("button", { name: "Preview report" }))
  await screen.findByText(/A selected note has changed/)
  expect(
    screen.queryByRole("button", { name: "Save report to case" })
  ).toBeNull()
  fireEvent.click(
    screen.getByRole("button", { name: "Use latest selected notes" })
  )
  await screen.findByText(/version 2/)
  await preview()
  expect(
    (screen.getByTitle("Financial report preview") as HTMLIFrameElement).srcdoc
  ).toContain("Saved note version 2")
})
it("retains work and prevents an immediate duplicate save after an uncertain response", async () => {
  const f = await setup()
  api.create.mockRejectedValue(Error("Connection interrupted"))
  await preview()
  fireEvent.click(screen.getByRole("button", { name: "Save report to case" }))
  await screen.findByText(/Connection interrupted/)
  expect(
    screen.getByRole("button", { name: "Save report to case" })
  ).toBeDisabled()
  expect(useFinancialDraftStore.getState().drafts[f.key]).toMatchObject({
    title: "Comparison for review",
    selected: [{ id: f.entry.id }],
  })
  expect(api.create).toHaveBeenCalledTimes(1)
})
it("does not discard a newer draft when an earlier save completes", async () => {
  const f = await setup()
  let finish!: (value: unknown) => void
  api.create.mockImplementation(
    () =>
      new Promise((resolve) => {
        finish = resolve
      })
  )
  await preview()
  fireEvent.click(screen.getByRole("button", { name: "Save report to case" }))
  await waitFor(() => expect(api.create).toHaveBeenCalledTimes(1))
  act(() =>
    useFinancialDraftStore
      .getState()
      .put(f.key, { title: "Next report", introduction: "", selected: [] })
  )
  await act(async () => finish({ ...f.entry, id: "report-created" }))
  expect(useFinancialDraftStore.getState().drafts[f.key]).toMatchObject({
    title: "Next report",
  })
})
