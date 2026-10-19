import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { beforeEach, expect, it, vi } from "vitest"
import { fetchAPI } from "@/lib/api-client"
import { ReadingProgress } from "./ReadingProgress"
import { readingSentence } from "../lib/review-queue"

vi.mock("@/lib/api-client", () => ({ fetchAPI: vi.fn() }))
vi.mock("../hooks/use-financial-access", () => ({
  useFinancialAccess: () => ({ canEdit: true, canUpload: true }),
}))
beforeEach(() => vi.mocked(fetchAPI).mockReset())

const progress = (over = {}) => ({
  files_total: 40,
  files_done: 11,
  files_reading: 29,
  files_waiting_to_start: 0,
  paused: false,
  unread_statement_files: 0,
  ...over,
})
const show = (reading: ReturnType<typeof progress>) =>
  render(
    <QueryClientProvider client={new QueryClient()}>
      <ReadingProgress caseId="case" reading={reading} />
    </QueryClientProvider>
  )

it("says how far reading has got, and nothing once it is done", () => {
  expect(readingSentence(progress())).toBe("Reading 12 of 40 files…")
  expect(readingSentence(progress({ paused: true }))).toBe("Reading paused at 11 of 40 files")
  expect(readingSentence(progress({ files_done: 40, files_reading: 0 }))).toBe("")
  const { container } = show(progress({ files_done: 40, files_reading: 0 }))
  expect(container.textContent).toBe("")
})

it("reads the unread statement files with one action", async () => {
  vi.mocked(fetchAPI).mockResolvedValue({ case_id: "case", added: 3, copies: 1, batch_id: "b" })
  show(progress({ files_reading: 0, files_done: 40, unread_statement_files: 4 }))
  fireEvent.click(screen.getByRole("button", { name: "Read 4 unread statement files" }))
  await waitFor(() => expect(screen.getByText(/3 files are being read/)).toBeTruthy())
  expect(vi.mocked(fetchAPI).mock.calls[0][0]).toBe(
    "/api/financial/statement-import/review/read-unread?case_id=case"
  )
  expect(screen.getByText(/1 copy of files already in Financial was not read again/)).toBeTruthy()
})
