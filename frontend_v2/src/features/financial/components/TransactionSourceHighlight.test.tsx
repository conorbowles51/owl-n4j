/**
 * The gate this component adds in front of `SourceHighlight`: fetch a page
 * image only for the two locator kinds that can use one, and only when a
 * source document id exists to fetch it from. Every other case must reach
 * `SourceHighlight` exactly as before, with no network call in between.
 */

import { render, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { TransactionSourceHighlight } from "./TransactionSourceHighlight"

/** A stored payload as `Locator.to_json` writes it, US-Letter page. */
function rectanglePayload(page = 3): Record<string, unknown> {
  return {
    kind: "page_rectangle",
    page,
    rect: [153000, 198000, 306000, 396000],
    page_size: [612000, 792000],
    units: "millipoints",
    space: "pdf_displayed",
  }
}

describe("TransactionSourceHighlight", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn())
    vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:mock-page-image")
    vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => {})
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  describe("locator kinds with nothing to draw an image under", () => {
    it("never fetches for not_positional, and shows its own sentence", () => {
      render(
        <TransactionSourceHighlight
          locatorPayload={{ kind: "not_positional" }}
          sourceDocumentId="doc-1"
        />,
      )
      expect(globalThis.fetch).not.toHaveBeenCalled()
      expect(screen.getByTestId("locator-not-positional")).toBeTruthy()
    })

    it("never fetches for unlocated, even with a page on it", () => {
      render(
        <TransactionSourceHighlight
          locatorPayload={{ kind: "unlocated", page: 7 }}
          sourceDocumentId="doc-1"
        />,
      )
      expect(globalThis.fetch).not.toHaveBeenCalled()
      expect(screen.getByTestId("locator-unlocated").textContent).toContain("page 7")
    })

    it("never fetches for a payload readLocator refuses", () => {
      render(
        <TransactionSourceHighlight
          locatorPayload={{ kind: "paragraph" }}
          sourceDocumentId="doc-1"
        />,
      )
      expect(globalThis.fetch).not.toHaveBeenCalled()
      expect(screen.getByTestId("locator-unreadable")).toBeTruthy()
    })
  })

  describe("locator kinds that need an image, but have nowhere to fetch it from", () => {
    it("does not fetch when no source document id is on the row", () => {
      render(
        <TransactionSourceHighlight
          locatorPayload={{ kind: "page_only", page: 12 }}
          sourceDocumentId={null}
        />,
      )
      expect(globalThis.fetch).not.toHaveBeenCalled()
      const sentence = screen.getByTestId("locator-page-only")
      expect(sentence.textContent).toContain("page 12")
      expect(screen.queryByRole("img")).toBeNull()
    })
  })

  describe("page_only with a source document id", () => {
    it("shows a loading state, then the fetched page with no box on it", async () => {
      vi.mocked(globalThis.fetch).mockResolvedValue(
        new Response("fake-png-bytes", { status: 200, headers: { "Content-Type": "image/png" } }),
      )

      render(
        <TransactionSourceHighlight
          locatorPayload={{ kind: "page_only", page: 12 }}
          sourceDocumentId="doc-1"
        />,
      )

      expect(screen.getByText("Loading the source page...")).toBeTruthy()

      const image = await screen.findByAltText("Page 12 of the source document")
      expect(image.getAttribute("src")).toBe("blob:mock-page-image")
      expect(screen.queryByTestId("locator-highlight-box")).toBeNull()

      expect(globalThis.fetch).toHaveBeenCalledWith(
        "/api/evidence/doc-1/page/12/image",
        expect.objectContaining({ credentials: "include" }),
      )
    })
  })

  describe("page_rectangle with a source document id", () => {
    it("fetches the right page and draws the box once the image resolves", async () => {
      vi.mocked(globalThis.fetch).mockResolvedValue(
        new Response("fake-png-bytes", { status: 200, headers: { "Content-Type": "image/png" } }),
      )

      render(
        <TransactionSourceHighlight
          locatorPayload={rectanglePayload(3)}
          sourceDocumentId="doc-1"
          valueLabel="the $1,250.00 amount"
        />,
      )

      await waitFor(() => {
        expect(globalThis.fetch).toHaveBeenCalledWith(
          "/api/evidence/doc-1/page/3/image",
          expect.objectContaining({ credentials: "include" }),
        )
      })

      const box = await screen.findByTestId("locator-highlight-box")
      expect(box.style.left).toBe("25%")
      expect(box.style.top).toBe("25%")
      expect(
        screen.getByLabelText("Highlighted source of the $1,250.00 amount on page 3"),
      ).toBeTruthy()
    })

    it("falls back to the no-image sentence if the fetch fails", async () => {
      vi.mocked(globalThis.fetch).mockResolvedValue(new Response(null, { status: 404 }))

      render(
        <TransactionSourceHighlight
          locatorPayload={rectanglePayload(3)}
          sourceDocumentId="doc-1"
        />,
      )

      const sentence = await screen.findByTestId("locator-no-page-image")
      expect(sentence.textContent).toContain("page 3 is recorded")
      expect(screen.queryByTestId("locator-highlight")).toBeNull()
    })
  })
})
