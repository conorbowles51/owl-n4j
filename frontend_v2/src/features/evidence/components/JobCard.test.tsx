import { fireEvent, render, screen } from "@testing-library/react"
import { expect, it, vi } from "vitest"
import type { EvidenceJob } from "@/types/evidence.types"
import { JobCard } from "./JobCard"

const job: EvidenceJob = {
  id: "reading-job",
  case_id: "synthetic-case",
  batch_id: null,
  job_type: "pdf_review",
  evidence_file_id: "retained-reading",
  file_name: "Synthetic statement.pdf",
  status: "failed",
  progress: 0,
  error_message: "Synthetic reading failure",
  entity_count: 0,
  relationship_count: 0,
  file_size: 100,
  mime_type: "application/pdf",
  sha256: null,
  created_at: "2026-09-25T10:00:00Z",
  updated_at: "2026-09-25T10:00:01Z",
}

it("does not offer Retry or Clear when the containing workflow supplies no action", () => {
  render(<JobCard job={job} />)
  expect(screen.getByText("Failed")).toBeVisible()
  expect(
    screen.queryByRole("button", { name: "Retry" })
  ).not.toBeInTheDocument()
  expect(
    screen.queryByRole("button", { name: "Clear" })
  ).not.toBeInTheDocument()
})

it("does not offer unsupported pause or resume controls in a read-only workflow", () => {
  const view = render(<JobCard job={{ ...job, resumable: true }} />)
  expect(
    screen.queryByRole("button", { name: "Resume" })
  ).not.toBeInTheDocument()
  view.rerender(
    <JobCard job={{ ...job, resumable: true, status: "extracting_text" }} />
  )
  expect(
    screen.queryByRole("button", { name: "Pause" })
  ).not.toBeInTheDocument()
})

it("invokes supplied actions for the exact reading and blocks repeat requests while pending", () => {
  const retry = vi.fn(),
    clear = vi.fn()
  const view = render(<JobCard job={job} onRetry={retry} onClear={clear} />)
  fireEvent.click(screen.getByRole("button", { name: "Retry" }))
  fireEvent.click(screen.getByRole("button", { name: "Clear" }))
  expect(retry).toHaveBeenCalledWith(job)
  expect(clear).toHaveBeenCalledWith(job)
  view.rerender(
    <JobCard job={job} onRetry={retry} onClear={clear} retrying clearing />
  )
  expect(screen.getByRole("button", { name: "Retry" })).toBeDisabled()
  expect(screen.getByRole("button", { name: "Clear" })).toBeDisabled()
  fireEvent.click(screen.getByRole("button", { name: "Retry" }))
  expect(retry).toHaveBeenCalledTimes(1)
})
