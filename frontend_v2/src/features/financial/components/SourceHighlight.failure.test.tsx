import { fireEvent, render, screen } from "@testing-library/react"
import { afterEach, expect, it, vi } from "vitest"
import { SourceHighlight } from "./SourceHighlight"
import { TransactionSourceHighlight } from "./TransactionSourceHighlight"

afterEach(() => vi.restoreAllMocks())
const rectangle = {
  kind: "page_rectangle",
  page: 1,
  rect: [1, 1, 2, 2],
  page_size: [10, 10],
  units: "millipoints",
  space: "pdf_displayed",
}
it.each([{ kind: "page_only", page: 1 }, rectangle])(
  "reports image decoding failure and recovers for another image %j",
  (payload) => {
    const view = render(
      <SourceHighlight payload={payload} pageImageUrl="blob:first" />
    )
    fireEvent.error(screen.getByAltText("Page 1 of the source document"))
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Source page 1 could not be displayed"
    )
    expect(screen.queryByTestId("locator-highlight-box")).toBeNull()
    expect(screen.queryByAltText("Page 1 of the source document")).toBeNull()
    view.rerender(
      <SourceHighlight payload={payload} pageImageUrl="blob:second" />
    )
    expect(screen.queryByRole("alert")).toBeNull()
    expect(
      screen.getByAltText("Page 1 of the source document")
    ).toHaveAttribute("src", "blob:second")
  }
)
it("does not claim a page is shown when no image was supplied", () => {
  render(<SourceHighlight payload={{ kind: "page_only", page: 4 }} />)
  expect(screen.getByTestId("locator-page-only")).toHaveTextContent(
    "No rendering of the page is available"
  )
  expect(screen.getByTestId("locator-page-only")).not.toHaveTextContent(
    "page is shown"
  )
})
it("reports a page-only HTTP failure rather than saying the page is shown", async () => {
  const fetch = vi
    .spyOn(globalThis, "fetch")
    .mockResolvedValue(new Response(null, { status: 503 }))
  render(
    <TransactionSourceHighlight
      locatorPayload={{ kind: "page_only", page: 4 }}
      sourceDocumentId="file"
    />
  )
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Source page 4 could not be loaded"
  )
  expect(screen.queryByTestId("locator-page-only")).toBeNull()
  expect(fetch).toHaveBeenCalledTimes(1)
})
