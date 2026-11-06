import { fireEvent, render, screen } from "@testing-library/react"
import { expect, it, vi } from "vitest"
import type { EvidenceJob } from "@/types/evidence.types"
import { CANCEL_JOB_KEEPS, JobCard } from "./JobCard"

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

it("a job that finished while a release flagged it paused reads as finished, not paused", () => {
  const done = { ...job, job_type: "ingestion", status: "completed", error_message: null, resumable: true, paused: true } as EvidenceJob
  render(<JobCard job={done} onResume={vi.fn()} onPause={vi.fn()} />)
  expect(screen.queryByText("Paused")).not.toBeInTheDocument()
  expect(screen.queryByRole("button", { name: "Resume" })).not.toBeInTheDocument()
})

const running: EvidenceJob = { ...job, job_type: "ingestion", status: "chunking", resumable: true, error_message: null }

it("offers Cancel on a running ingestion, confirms it, then asks once", () => {
  const onCancel = vi.fn()
  render(<JobCard job={{ ...running, batch_id: "b" }} onCancel={onCancel} onPause={vi.fn()} />)
  fireEvent.click(screen.getByRole("button", { name: "Cancel batch" }))
  expect(onCancel).not.toHaveBeenCalled()
  expect(screen.getByText(CANCEL_JOB_KEEPS)).toBeVisible()
  fireEvent.click(screen.getByRole("button", { name: "Cancel processing" }))
  expect(onCancel).toHaveBeenCalledTimes(1)
})

it.each(["pdf_review", "audio_review"])("offers Cancel on %s", (job_type) => {
  render(<JobCard job={{ ...running, job_type }} onCancel={vi.fn()} />)
  expect(screen.getByRole("button", { name: "Cancel" })).toBeVisible()
})

it("offers no Cancel, Pause or Resume on a kind that cannot do them", () => {
  render(
    <JobCard
      job={{ ...running, job_type: "entity_merge", status: "failed", error_message: "Merge failed" }}
      onCancel={vi.fn()}
      onPause={vi.fn()}
      onResume={vi.fn()}
    />
  )
  for (const name of ["Cancel", "Pause", "Resume"])
    expect(screen.queryByRole("button", { name })).not.toBeInTheDocument()
})

it("shows Cancelling with no controls while the worker finishes its step", () => {
  render(
    <JobCard job={{ ...running, cancel_requested: true }} onCancel={vi.fn()} onPause={vi.fn()} onResume={vi.fn()} />
  )
  expect(screen.getByText("Cancelling")).toBeVisible()
  expect(screen.queryByRole("button", { name: /Cancel|Pause|Resume/ })).not.toBeInTheDocument()
})

it("once writing to the case has begun it says so and offers no Cancel", () => {
  render(<JobCard job={{ ...running, pipeline_state: { publication_begun: true } }} onCancel={vi.fn()} />)
  expect(screen.getByText("Writing to the case. This can no longer be cancelled.")).toBeVisible()
  expect(screen.queryByRole("button", { name: "Cancel" })).not.toBeInTheDocument()
})

it("a cancelled job reads as cancelled with its counts, not as a failure, and can be run again", () => {
  const words = "Cancelled on request. This file stays in the case. In this batch of 5: 3 cancelled, 2 finished."
  render(
    <JobCard
      job={{
        ...running,
        status: "failed",
        cancel_requested: true,
        cancelled_at: "2026-11-05T23:00:00",
        error_message: words,
        resumable: true,
      }}
      onRetry={vi.fn()}
      onResume={vi.fn()}
      onClear={vi.fn()}
    />
  )
  expect(screen.getByText("Cancelled")).toBeVisible()
  expect(screen.getByText(words)).toBeVisible()
  expect(screen.queryByText("Failed")).not.toBeInTheDocument()
  expect(screen.queryByText("Processing stopped before completion.")).not.toBeInTheDocument()
  expect(screen.queryByRole("button", { name: "Resume" })).not.toBeInTheDocument()
  expect(screen.getByRole("button", { name: "Retry" })).toBeVisible()
  expect(screen.getByRole("button", { name: "Clear" })).toBeVisible()
})

it("a release pause reads as paused, never as cancelled", () => {
  render(<JobCard job={{ ...running, status: "pending", paused: true }} onCancel={vi.fn()} onResume={vi.fn()} />)
  expect(screen.getByText("Paused")).toBeVisible()
  expect(screen.queryByText("Cancelled")).not.toBeInTheDocument()
})
