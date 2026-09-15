import { fireEvent, render, screen } from "@testing-library/react"
import { expect, it, vi } from "vitest"
import type { Transaction } from "../api"
import { TransactionDetailPanel } from "./TransactionDetailPanel"

vi.mock("./TransactionSourceHighlight", () => ({
  TransactionSourceHighlight: () => <p>No exact position recorded</p>,
}))
vi.mock("@/components/ui/document-viewer", () => ({
  DocumentViewer: ({
    open,
    documentUrl,
    documentName,
    initialPage,
    caseId,
    evidenceId,
    onOpenChange,
  }: {
    open: boolean
    documentUrl: string
    documentName: string
    initialPage: number
    caseId?: string
    evidenceId?: string
    onOpenChange: (open: boolean) => void
  }) =>
    open ? (
      <section aria-label="Original file viewer">
        <a href={documentUrl}>{documentName}</a>
        <p>Page {initialPage}</p>
        {caseId && evidenceId && (
          <a href={`/cases/${caseId}/evidence?file=${evidenceId}`}>
            Open file location
          </a>
        )}
        <button onClick={() => onOpenChange(false)}>Close original</button>
      </section>
    ) : null,
}))

it("opens the linked original at its recorded page even without an exact text location", () => {
  const transaction = {
    key: "receipt",
    name: "Receipt",
    amount: 120,
    currency: "USD",
    financial_record_kind: "allegation",
    source_document_id: "source-file",
    source_filename: "receipt.pdf",
    source_page: 2,
  } as Transaction
  render(
    <TransactionDetailPanel
      caseId="case-a"
      transaction={transaction}
      editable={false}
      onSave={vi.fn()}
    />
  )
  expect(
    screen.queryByRole("region", { name: "Original file viewer" })
  ).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole("button", { name: "Open original file" }))
  expect(screen.getByRole("link", { name: "receipt.pdf" })).toHaveAttribute(
    "href",
    "/api/evidence/source-file/file"
  )
  expect(screen.getByText("Page 2")).toBeVisible()
  expect(
    screen.getByRole("link", { name: "Open file location" })
  ).toHaveAttribute("href", "/cases/case-a/evidence?file=source-file")
  fireEvent.click(screen.getByRole("button", { name: "Close original" }))
  expect(
    screen.queryByRole("region", { name: "Original file viewer" })
  ).not.toBeInTheDocument()
  expect(
    screen.getByRole("region", { name: "Record details for Receipt" })
  ).toBeVisible()
})
