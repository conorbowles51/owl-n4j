import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, expect, it, vi } from "vitest"
import { CandidateAccountForm } from "./CandidateAccountForm"
afterEach(() => vi.restoreAllMocks())
function mount(currency = "GBP") {
  const onCreated = vi.fn(),
    onBusy = vi.fn()
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  const view = render(
    <QueryClientProvider client={client}>
      <CandidateAccountForm
        caseId="case-a"
        candidateId="candidate-a"
        fileId="file-a"
        reviewRevision={"a".repeat(64)}
        currency={currency}
        disabled={false}
        onCreated={onCreated}
        onBusy={onBusy}
      />
    </QueryClientProvider>
  )
  fireEvent.click(
    screen.getByRole("button", { name: "Set up a provisional account" })
  )
  return { ...view, onCreated, onBusy, client }
}
function server({ status = 200, wrongCase = false } = {}) {
  return vi.spyOn(globalThis, "fetch").mockImplementation(
    async () =>
      new Response(
        JSON.stringify(
          status === 200
            ? {
                case_id: wrongCase ? "case-b" : "case-a",
                candidate_id: "candidate-a",
                evidence_file_id: "file-a",
                review_revision: "a".repeat(64),
                applied: false,
                created: true,
                run_id: "run-a",
                account: {
                  id: "account-a",
                  identifier: null,
                  holder: null,
                  institution: null,
                  currency: "GBP",
                  display_label: "Redacted card A",
                  provisional: true,
                  source_file_id: "file-a",
                },
              }
            : { detail: "Review changed; reload." }
        ),
        { status, headers: { "Content-Type": "application/json" } }
      )
  )
}
function fill() {
  fireEvent.change(screen.getByLabelText("Provisional account label"), {
    target: { value: "Redacted card A" },
  })
  fireEvent.change(screen.getByLabelText("Reason for provisional account"), {
    target: { value: "Number is redacted" },
  })
}
it("requires a label, reason and currency without guessing an identifier", () => {
  server()
  mount("")
  fill()
  expect(
    screen.getByRole("button", { name: "Create provisional account" })
  ).toBeDisabled()
  expect(screen.getByText(/not a printed account number/)).toBeVisible()
})
it("creates once with the displayed revision and records the selected account", async () => {
  const fetch = server()
  const { onCreated, onBusy } = mount()
  fill()
  const button = screen.getByRole("button", {
    name: "Create provisional account",
  })
  fireEvent.click(button)
  fireEvent.click(button)
  await waitFor(() =>
    expect(onCreated).toHaveBeenCalledWith(
      expect.objectContaining({ id: "account-a", provisional: true })
    )
  )
  expect(fetch).toHaveBeenCalledTimes(1)
  expect(JSON.parse(String(fetch.mock.calls[0][1]?.body))).toEqual({
    label: "Redacted card A",
    reason: "Number is redacted",
    currency: "GBP",
    expected_revision: "a".repeat(64),
  })
  expect(onBusy.mock.calls).toEqual([[true], [false]])
  expect(button).toBeDisabled()
})
it("requires review reload after a stale or uncertain write", async () => {
  server({ status: 409 })
  const { onCreated } = mount()
  fill()
  fireEvent.click(
    screen.getByRole("button", { name: "Create provisional account" })
  )
  expect(await screen.findByRole("alert")).toHaveTextContent("Review changed")
  expect(screen.getByLabelText("Provisional account label")).toBeDisabled()
  expect(onCreated).not.toHaveBeenCalled()
})
it("refuses account data from another case", async () => {
  server({ wrongCase: true })
  const { onCreated } = mount()
  fill()
  fireEvent.click(
    screen.getByRole("button", { name: "Create provisional account" })
  )
  expect(await screen.findByRole("alert")).toBeVisible()
  expect(onCreated).not.toHaveBeenCalled()
})
it("retains original case invalidation after the form closes during a write", async () => {
  const fetch = server()
  const { client, unmount } = mount()
  fill()
  const invalidate = vi.spyOn(client, "invalidateQueries"),
    respond = fetch.getMockImplementation()!
  let release!: () => void
  fetch.mockImplementation(async (url, options) => {
    await new Promise<void>((resolve) => {
      release = resolve
    })
    return respond(url, options)
  })
  fireEvent.click(
    screen.getByRole("button", { name: "Create provisional account" })
  )
  await waitFor(() => expect(release).toBeDefined())
  unmount()
  release()
  await waitFor(() =>
    expect(invalidate).toHaveBeenCalledWith({
      queryKey: ["financial-candidates", "case-a", "accounts"],
    })
  )
})
