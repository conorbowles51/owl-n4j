import { fireEvent, render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import { collectSummarySources } from "@/lib/summary-sources"
import { MarkdownSummary } from "./markdown-summary"

describe("compact summary citations", () => {
  it("shows compact markers and opens each occurrence at its original page", () => {
    const summary = collectSummarySources(
      "Paid [Lengthy filename](doc://report%20name.pdf/4), then [same report](doc://report%20name.pdf/7)."
    )
    const open = vi.fn()
    render(
      <MarkdownSummary
        content={summary.content}
        sourceNumbers={summary.numbers}
        onOpenFile={open}
      />
    )
    expect(screen.queryByText("Lengthy filename")).not.toBeInTheDocument()
    expect(screen.getByText("[S1, p.4]")).toHaveAttribute(
      "title",
      "report name.pdf, p.4"
    )
    fireEvent.click(screen.getByText("[S1, p.4]"))
    expect(open).toHaveBeenLastCalledWith("report name.pdf", 4)
    fireEvent.click(screen.getByText("[S1, p.7]"))
    expect(open).toHaveBeenLastCalledWith("report name.pdf", 7)
  })

  it("keeps the original labels for other MarkdownSummary users", () => {
    const open = vi.fn()
    render(
      <MarkdownSummary
        content="Read [report.pdf](evidence://report.pdf) and [website](https://example.com)."
        onOpenFile={open}
      />
    )
    fireEvent.click(screen.getByRole("button", { name: "report.pdf" }))
    expect(open).toHaveBeenCalledWith("report.pdf", undefined)
    expect(screen.getByRole("link", { name: "website" })).toHaveAttribute(
      "href",
      "https://example.com"
    )
    expect(screen.queryByText("[S1]")).not.toBeInTheDocument()
  })
})
