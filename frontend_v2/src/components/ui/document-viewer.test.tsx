import { fireEvent, render, screen } from "@testing-library/react"
import { expect, it, vi } from "vitest"
import { DocumentViewer } from "./document-viewer"

vi.mock("@/lib/protected-file", () => ({
  openProtectedFile: vi.fn(),
  useProtectedObjectUrl: () => ({
    objectUrl: "blob:original",
    loading: false,
    error: null,
  }),
}))
vi.mock("./evidence-pdf-page", () => ({
  EvidencePdfPage: ({
    evidenceId,
    page,
    onPageCount,
  }: {
    evidenceId: string
    page: number
    onPageCount: (id: string, count: number) => void
  }) => (
    <button onClick={() => onPageCount(evidenceId, 3)}>
      Read source page {page}
    </button>
  ),
}))

it("preserves the existing document URL viewer when no evidence ID is available", () => {
  render(
    <DocumentViewer
      open
      onOpenChange={vi.fn()}
      documentUrl="/original.pdf"
      documentName="original.pdf"
    />
  )
  expect(screen.getByRole("heading", { name: "original.pdf" })).toBeVisible()
  expect(document.querySelector("iframe")).toHaveAttribute(
    "src",
    "blob:original#page=1"
  )
  expect(
    screen.getByRole("button", { name: "Previous PDF page" })
  ).toBeDisabled()
})

it("uses the source page count to stop navigation at the first and last page", () => {
  render(
    <DocumentViewer
      open
      onOpenChange={vi.fn()}
      documentUrl="/source.pdf"
      documentName="source.pdf"
      evidenceId="source"
      initialPage={2}
    />
  )
  expect(document.querySelector("iframe")).toBeNull()
  fireEvent.click(screen.getByRole("button", { name: "Read source page 2" }))
  expect(screen.getByText("Page 2 of 3")).toBeVisible()
  fireEvent.click(screen.getByRole("button", { name: "Next PDF page" }))
  expect(screen.getByRole("button", { name: "Next PDF page" })).toBeDisabled()
  fireEvent.click(screen.getByRole("button", { name: "Previous PDF page" }))
  fireEvent.click(screen.getByRole("button", { name: "Previous PDF page" }))
  expect(
    screen.getByRole("button", { name: "Previous PDF page" })
  ).toBeDisabled()
  expect(screen.getByText("Page 1 of 3")).toBeVisible()
})
