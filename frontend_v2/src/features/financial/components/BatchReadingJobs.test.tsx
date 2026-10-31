import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, waitFor } from "@testing-library/react"
import { expect, it, vi } from "vitest"
import { fetchAPI } from "@/lib/api-client"
import { BatchReadingJobs } from "./BatchReadingJobs"
vi.mock("@/lib/api-client", () => ({ fetchAPI: vi.fn() }))
vi.mock("@/features/evidence/components/JobCard", () => ({
  JobCard: ({ job }: { job: { id: string } }) => <div>job {job.id}</div>,
}))

const done = { id: "old", status: "completed", job_type: "pdf_review", progress: 1 }
const started = { id: "new", status: "extracting_text", job_type: "pdf_review", progress: 0 }

it("fetches the job list again when the batch names a reading the list does not have yet", async () => {
  const lists = [[done], [done, started]]
  vi.mocked(fetchAPI).mockImplementation(async () => lists.shift() ?? [done, started])
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const view = (jobIds: string[]) => (
    <QueryClientProvider client={client}>
      <BatchReadingJobs caseId="case" jobIds={jobIds} canEdit />
    </QueryClientProvider>
  )
  const { rerender, findByText } = render(view(["old"]))
  await findByText("job old")
  expect(fetchAPI).toHaveBeenCalledTimes(1)

  // The server started a reading (a retry, or the automatic sweep): the batch now names it.
  rerender(view(["old", "new"]))
  await findByText("job new")
  await waitFor(() => expect(fetchAPI).toHaveBeenCalledTimes(2))
})
