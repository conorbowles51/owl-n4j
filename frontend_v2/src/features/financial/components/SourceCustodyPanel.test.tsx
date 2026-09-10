import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, expect, it, vi } from "vitest"
import { SourceCustodyPanel } from "./SourceCustodyPanel"
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
const response = (value: unknown, status = 200) =>
  new Response(JSON.stringify(value), { status })
function mount() {
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
      <SourceCustodyPanel caseId={caseId} fileId={fileId} />
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
