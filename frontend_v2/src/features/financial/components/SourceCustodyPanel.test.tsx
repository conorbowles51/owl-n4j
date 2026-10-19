// This existing workflow fixture has case editing and upload access.
vi.mock("../hooks/use-financial-access", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../hooks/use-financial-access")>()),
  useFinancialAccess: () => ({
    canEdit: true,
    canUpload: true,
    ready: true,
    error: false,
  }),
}))
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, expect, it, vi } from "vitest"
import { SourceCustodyPanel } from "./SourceCustodyPanel"
import { useFinancialDraftStore } from "../stores/financial-drafts"
const caseId = "11111111-1111-4111-8111-111111111111"
const fileId = "22222222-2222-4222-8222-222222222222"
const initial = {
  case_id: caseId,
  evidence_file_id: fileId,
  evidence_sha256: "a".repeat(64),
  events: [],
  limitation: "Reported history only.",
}
afterEach(() => vi.restoreAllMocks())
beforeEach(() => useFinancialDraftStore.setState({ drafts: {} }))
const response = (value: unknown, status = 200) =>
  new Response(JSON.stringify(value), { status })
function mount(caseValue = caseId, fileValue = fileId) {
  return render(
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
      <SourceCustodyPanel caseId={caseValue} fileId={fileValue} />
    </QueryClientProvider>
  )
}
async function open() {
  fireEvent.click(
    screen.getByRole("button", { name: "Source custody records" })
  )
  await screen.findByText(
    "No custody reports recorded. Earlier custody is unknown."
  )
}
it("loads only when opened and rejects history from another source", async () => {
  const fetch = vi
    .spyOn(globalThis, "fetch")
    .mockResolvedValue(response({ ...initial, evidence_file_id: caseId }))
  mount()
  expect(fetch).not.toHaveBeenCalled()
  fireEvent.click(
    screen.getByRole("button", { name: "Source custody records" })
  )
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "do not match this source"
  )
  expect(
    screen.queryByRole("button", { name: "Record custody report" })
  ).toBeNull()
})
it("requires explicit timezone and retains the same identifier on a failed submission retry", async () => {
  const fetch = vi
    .spyOn(globalThis, "fetch")
    .mockResolvedValueOnce(response(initial))
    .mockResolvedValue(response({ detail: "Temporarily unavailable" }, 503))
  mount()
  await open()
  fireEvent.change(screen.getByLabelText("Received by"), {
    target: { value: "Test recipient" },
  })
  fireEvent.change(screen.getByLabelText("Details and reason"), {
    target: { value: "Synthetic report" },
  })
  const time = screen.getByLabelText(
    "Reported event time with timezone (optional)"
  )
  fireEvent.change(time, { target: { value: "2026-09-10T12:00:00" } })
  fireEvent.click(screen.getByRole("button", { name: "Record custody report" }))
  expect(await screen.findByRole("status")).toHaveTextContent(
    "explicit timezone"
  )
  expect(fetch).toHaveBeenCalledTimes(1)
  fireEvent.change(time, { target: { value: "2026-09-10T12:00:00+01:00" } })
  fireEvent.click(screen.getByRole("button", { name: "Record custody report" }))
  await screen.findByRole("alert")
  fireEvent.click(screen.getByRole("button", { name: "Record custody report" }))
  await waitFor(() => expect(fetch).toHaveBeenCalledTimes(3))
  const first = JSON.parse(String(fetch.mock.calls[1][1]?.body))
  const second = JSON.parse(String(fetch.mock.calls[2][1]?.body))
  expect(second).toEqual(first)
  expect(first.expected_source_sha256).toBe("a".repeat(64))
  expect(first).not.toHaveProperty("actor")
})
it("preserves the prior report while selecting a correction", async () => {
  const id = "33333333-3333-4333-8333-333333333333"
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    response({
      ...initial,
      events: [
        {
          id,
          case_id: caseId,
          evidence_file_id: fileId,
          evidence_sha256: "a".repeat(64),
          recorded_at: "2026-09-10T12:00:00Z",
          actor: {
            name: "Tester",
            email: "tester@example.invalid",
            user_id: null,
          },
          report: {
            event_kind: "receipt",
            occurred_at: null,
            received_by: "Tester",
            from_person_or_organisation: null,
            acquisition_method: "unknown",
            native_file_status: "unknown",
            certification_file_id: null,
            certification_sha256: null,
            corrects_event_id: null,
            reason: "Original report",
          },
        },
      ],
    })
  )
  mount()
  fireEvent.click(
    screen.getByRole("button", { name: "Source custody records" })
  )
  fireEvent.click(
    await screen.findByRole("button", { name: "Correct this custody report" })
  )
  expect(screen.getByLabelText("Report type")).toHaveValue("correction")
  expect(screen.getByText("Original report")).toBeVisible()
  expect(screen.getByText(/Correcting report/)).toHaveTextContent(id)
})

it("loads certification files by name and excludes the source itself", async () => {
  const certificate = "44444444-4444-4444-8444-444444444444"
  const fetch = vi
    .spyOn(globalThis, "fetch")
    .mockResolvedValueOnce(response(initial))
    .mockResolvedValueOnce(
      response({
        files: [
          { id: fileId, original_filename: "Original statement.pdf" },
          { id: certificate, original_filename: "Custodian certification.pdf" },
        ],
      })
    )
  mount()
  await open()
  fireEvent.click(
    screen.getByRole("button", {
      name: "Choose a certification file from this case",
    })
  )
  await screen.findByRole("option", { name: "Custodian certification.pdf" })
  expect(
    screen.queryByRole("option", { name: "Original statement.pdf" })
  ).toBeNull()
  fireEvent.change(screen.getByLabelText("Supporting certification file"), {
    target: { value: certificate },
  })
  expect(screen.getByLabelText("Supporting certification file")).toHaveValue(
    certificate
  )
  expect(String(fetch.mock.calls[1][0])).toContain(`case_id=${caseId}`)
})

function fillReport() {
  fireEvent.change(screen.getByLabelText("Received by"), {
    target: { value: "Synthetic investigator" },
  })
  fireEvent.change(screen.getByLabelText("Received from (optional)"), {
    target: { value: "Synthetic document provider" },
  })
  fireEvent.change(
    screen.getByLabelText("Reported event time with timezone (optional)"),
    { target: { value: "2026-09-15T10:30:00+01:00" } }
  )
  fireEvent.change(screen.getByLabelText("How obtained"), {
    target: { value: "client" },
  })
  fireEvent.change(screen.getByLabelText("Native file availability"), {
    target: { value: "requested" },
  })
  fireEvent.change(screen.getByLabelText("Details and reason"), {
    target: { value: "Synthetic source receipt to check recovery." },
  })
}
const recordButton = () =>
  screen.getByRole("button", { name: "Record custody report" })
function savedEvent(body: Record<string, unknown>) {
  const { event_id, expected_source_sha256, ...report } = body
  return {
    id: event_id,
    case_id: caseId,
    evidence_file_id: fileId,
    evidence_sha256: expected_source_sha256,
    recorded_at: "2026-09-15T10:00:00Z",
    actor: { name: "Tester", email: "tester@example.invalid", user_id: null },
    report: { ...report, certification_sha256: null },
  }
}

it("restores every unfinished field after closing and keeps other sources separate", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(response(initial))
  const first = mount()
  await open()
  fillReport()
  fireEvent.click(
    screen.getByRole("button", { name: "Source custody records" })
  )
  await open()
  expect(screen.getByLabelText("Received by")).toHaveValue(
    "Synthetic investigator"
  )
  expect(screen.getByLabelText("Received from (optional)")).toHaveValue(
    "Synthetic document provider"
  )
  expect(
    screen.getByLabelText("Reported event time with timezone (optional)")
  ).toHaveValue("2026-09-15T10:30:00+01:00")
  expect(screen.getByLabelText("How obtained")).toHaveValue("client")
  expect(screen.getByLabelText("Native file availability")).toHaveValue(
    "requested"
  )
  first.unmount()
  const otherFile = "44444444-4444-4444-8444-444444444444"
  vi.mocked(globalThis.fetch).mockResolvedValue(
    response({ ...initial, evidence_file_id: otherFile })
  )
  const other = mount(caseId, otherFile)
  await open()
  expect(screen.getByLabelText("Details and reason")).toHaveValue("")
  other.unmount()
  vi.mocked(globalThis.fetch).mockResolvedValue(response(initial))
  mount()
  await open()
  expect(screen.getByLabelText("Details and reason")).toHaveValue(
    "Synthetic source receipt to check recovery."
  )
})

it("retains the request ID after a failed save and remount, then clears the confirmed draft", async () => {
  const bodies: Record<string, unknown>[] = []
  vi.spyOn(globalThis, "fetch").mockImplementation(async (_url, options) => {
    if (options?.method !== "POST") return response(initial)
    const body = JSON.parse(String(options.body))
    bodies.push(body)
    return bodies.length === 1
      ? response({ detail: "Connection interrupted" }, 503)
      : response(savedEvent(body))
  })
  const first = mount()
  await open()
  fillReport()
  fireEvent.click(recordButton())
  await screen.findByRole("alert")
  first.unmount()
  mount()
  await open()
  fireEvent.click(recordButton())
  await screen.findByText(
    "Custody report recorded. Earlier reports remain preserved."
  )
  expect(bodies).toHaveLength(2)
  expect(bodies[1]).toEqual(bodies[0])
  expect(screen.getByLabelText("Details and reason")).toHaveValue("")
})

it("requires current-source review before reusing a draft against a changed file hash", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(response(initial))
  const first = mount()
  await open()
  fillReport()
  first.unmount()
  vi.mocked(globalThis.fetch).mockResolvedValue(
    response({ ...initial, evidence_sha256: "b".repeat(64) })
  )
  mount()
  await open()
  expect(recordButton()).toBeDisabled()
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "source file changed"
  )
  fireEvent.click(
    screen.getByRole("button", { name: "Use details for the current source" })
  )
  expect(recordButton()).toBeEnabled()
  expect(screen.getByLabelText("Details and reason")).toHaveValue(
    "Synthetic source receipt to check recovery."
  )
})

it("does not accept a saved response with different report details", async () => {
  vi.spyOn(globalThis, "fetch").mockImplementation(async (_url, options) => {
    if (options?.method !== "POST") return response(initial)
    const saved = savedEvent(JSON.parse(String(options.body)))
    return response({
      ...saved,
      report: { ...saved.report, reason: "A different report" },
    })
  })
  mount()
  await open()
  fillReport()
  fireEvent.click(recordButton())
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "does not match this submission"
  )
  expect(screen.getByLabelText("Details and reason")).toHaveValue(
    "Synthetic source receipt to check recovery."
  )
})

it("sends only once when the form is submitted again before the response", async () => {
  let finish!: (value: Response) => void
  const bodies: Record<string, unknown>[] = []
  vi.spyOn(globalThis, "fetch").mockImplementation(async (_url, options) => {
    if (options?.method !== "POST") return response(initial)
    bodies.push(JSON.parse(String(options.body)))
    return new Promise<Response>((resolve) => {
      finish = resolve
    })
  })
  mount()
  await open()
  fillReport()
  const form = recordButton().closest("form")!
  fireEvent.submit(form)
  fireEvent.submit(form)
  await waitFor(() => expect(bodies).toHaveLength(1))
  finish(response(savedEvent(bodies[0])))
  await screen.findByText(
    "Custody report recorded. Earlier reports remain preserved."
  )
})

it("keeps a selected certification visible after reopening before the file list reloads", async () => {
  const certificate = "44444444-4444-4444-8444-444444444444"
  vi.spyOn(globalThis, "fetch").mockImplementation(async (url) =>
    String(url).includes("/custody")
      ? response(initial)
      : response({ files: [{ id: certificate, original_filename: "Synthetic certification.pdf" }] })
  )
  const first = mount()
  await open()
  fireEvent.click(screen.getByRole("button", { name: "Choose a certification file from this case" }))
  await screen.findByRole("option", { name: "Synthetic certification.pdf" })
  fireEvent.change(screen.getByLabelText("Supporting certification file"), { target: { value: certificate } })
  first.unmount()
  mount()
  await open()
  expect(screen.getByLabelText("Supporting certification file")).toHaveValue(certificate)
  expect(screen.getByRole("option", { name: /Synthetic certification.pdf.*previous selection/ })).toBeVisible()
})

it("retains a correction's selected report and refuses a missing history target", async () => {
  const prior = savedEvent({
    event_id: "33333333-3333-4333-8333-333333333333",
    expected_source_sha256: initial.evidence_sha256,
    event_kind: "receipt", occurred_at: null, received_by: "Original recipient",
    from_person_or_organisation: "Document provider", acquisition_method: "production",
    native_file_status: "provided", certification_file_id: null, corrects_event_id: null,
    reason: "Original receipt",
  })
  vi.spyOn(globalThis, "fetch").mockResolvedValue(response({ ...initial, events: [prior] }))
  const first = mount()
  fireEvent.click(screen.getByRole("button", { name: "Source custody records" }))
  fireEvent.click(await screen.findByRole("button", { name: "Correct this custody report" }))
  expect(screen.getByLabelText("Received by")).toHaveValue("Original recipient")
  expect(screen.getByLabelText("How obtained")).toHaveValue("production")
  expect(screen.getByLabelText("Details and reason")).toHaveValue("")
  fireEvent.change(screen.getByLabelText("Details and reason"), { target: { value: "Correct the named recipient" } })
  first.unmount()
  vi.mocked(globalThis.fetch).mockResolvedValue(response(initial))
  mount()
  await open()
  expect(screen.getByLabelText("Report type")).toHaveValue("correction")
  expect(screen.getByLabelText("Details and reason")).toHaveValue("Correct the named recipient")
  expect(recordButton()).toBeDisabled()
  expect(screen.getByRole("alert")).toHaveTextContent("not in the current history")
})
