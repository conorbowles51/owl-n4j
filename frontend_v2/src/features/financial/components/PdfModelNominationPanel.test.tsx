import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { afterEach, expect, it, vi } from "vitest"
import { PdfModelNominationPanel } from "./PdfModelNominationPanel"
import { fetchAPI, ApiError } from "@/lib/api-client"
vi.mock("@/lib/api-client", () => ({
  fetchAPI: vi.fn(),
  ApiError: class extends Error {
    status = 500
  },
}))
const id = "11111111-1111-4111-8111-111111111111"
const revision = "a".repeat(64)
const source = {
  case_id: id,
  evidence_file_id: id,
  page_number: 1,
  table_index: 0,
  table_count: 1,
  source_revision: revision,
  table_source: "text_alignment" as const,
  geometry_source: "synthetic",
  text_origin: "unknown" as const,
  locator: {},
  columns: [0],
  rows: [],
  applied: false as const,
}
const history = {
  case_id: id,
  evidence_file_id: id,
  offset: 0,
  has_more: false,
  items: [],
  applied: false,
}
const pending = (attempt: string) => ({
  id: attempt,
  case_id: id,
  evidence_file_id: id,
  status: "pending",
  request: {
    schema_version: "pdf-cell-nomination-v1",
    execution_mode: "simulated_test",
    page_number: 1,
    table_index: 0,
    source_revision: revision,
    case_id: id,
    evidence_file_id: id,
    provider: "test",
    model_id: "synthetic",
    prompt_sha256: revision,
  },
  request_sha256: revision,
  result: null,
  error_code: null,
  created_at: "2026-09-10",
  completed_at: null,
  applied: false,
  limitation: "Proposals only",
})
function mount() {
  render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <PdfModelNominationPanel
        source={source}
        onSaved={vi.fn()}
        onSource={vi.fn()}
      />
    </QueryClientProvider>
  )
}
afterEach(() => vi.resetAllMocks())
it("does not request a model until the investigator explicitly asks", async () => {
  vi.mocked(fetchAPI).mockResolvedValue(history)
  mount()
  expect(fetchAPI).not.toHaveBeenCalled()
  fireEvent.click(
    screen.getByRole("button", { name: "Model-assisted row proposals" })
  )
  await waitFor(() => expect(fetchAPI).toHaveBeenCalledTimes(1))
  expect(
    vi.mocked(fetchAPI).mock.calls.every(([, options]) => !options?.method)
  ).toBe(true)
})
it("keeps an uncertain attempt ID and checking never resends the provider request", async () => {
  let attempt = ""
  vi.mocked(fetchAPI).mockImplementation(async (url, options) => {
    if (options?.method === "POST") {
      attempt = (options.body as { request_id: string }).request_id
      throw Error("Connection lost")
    }
    return url.includes(`model-nominations/${attempt}?`) && attempt
      ? pending(attempt)
      : history
  })
  mount()
  fireEvent.click(
    screen.getByRole("button", { name: "Model-assisted row proposals" })
  )
  fireEvent.click(
    screen.getByRole("button", { name: "Request AI proposals for this page" })
  )
  await screen.findByText(/Connection lost/)
  expect(
    screen.getByRole("button", { name: "Request AI proposals for this page" })
  ).toBeDisabled()
  fireEvent.click(
    screen.getByRole("button", { name: "Check saved model attempt" })
  )
  await screen.findByText(/Attempt status: pending/)
  expect(
    vi.mocked(fetchAPI).mock.calls.filter(([, o]) => o?.method === "POST")
  ).toHaveLength(1)
  expect(screen.getByText(/no external model ran/)).toBeTruthy()
})
it("closes an interrupted attempt without silently starting another model request", async () => {
  let attempt = ""
  vi.mocked(fetchAPI).mockImplementation(async (url, options) => {
    if (url.includes("/abandon?"))
      return {
        ...pending(attempt),
        status: "failed",
        error_code: "user_abandoned",
        completed_at: "2026-09-10",
      }
    if (options?.method === "POST") {
      attempt = (options.body as { request_id: string }).request_id
      return pending(attempt)
    }
    return history
  })
  mount()
  fireEvent.click(
    screen.getByRole("button", { name: "Model-assisted row proposals" })
  )
  fireEvent.click(
    screen.getByRole("button", { name: "Request AI proposals for this page" })
  )
  await screen.findByText(/Attempt status: pending/)
  fireEvent.click(
    screen.getByRole("button", { name: "Close interrupted model attempt" })
  )
  await screen.findByText(/user_abandoned/)
  expect(
    vi.mocked(fetchAPI).mock.calls.filter(([, o]) => o?.method === "POST")
  ).toHaveLength(2)
  expect(
    screen.getByRole("button", { name: "Start a separate model request" })
  ).toBeTruthy()
})

it("reuses the original request ID when the first request never reached storage", async () => {
  const attempts: string[] = []
  vi.mocked(fetchAPI).mockImplementation(async (url, options) => {
    if (options?.method === "POST") {
      const attempt = (options.body as { request_id: string }).request_id
      attempts.push(attempt)
      if (attempts.length === 1) throw Error("Connection lost")
      return pending(attempt)
    }
    if (attempts.length && url.includes(`model-nominations/${attempts[0]}?`)) {
      throw Object.assign(new ApiError("Not found", 404), { status: 404 })
    }
    return history
  })
  mount()
  fireEvent.click(
    screen.getByRole("button", { name: "Model-assisted row proposals" })
  )
  fireEvent.click(
    screen.getByRole("button", { name: "Request AI proposals for this page" })
  )
  await screen.findByText(/Connection lost/)
  fireEvent.click(
    screen.getByRole("button", { name: "Check saved model attempt" })
  )
  fireEvent.click(
    await screen.findByRole("button", {
      name: "Retry the same model request ID",
    })
  )
  await screen.findByText(/Attempt status: pending/)
  expect(attempts).toHaveLength(2)
  expect(attempts[0]).toBe(attempts[1])
})
