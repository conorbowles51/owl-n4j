/**
 * The five things SourceHighlight can say, each asserted separately.
 *
 * Four kinds of absence get four different sentences, because they call for
 * four different responses from an investigator; the fifth outcome is the
 * highlight itself, whose box must sit exactly where `normalised` puts it.
 * The style assertions use fractions chosen to be exact in binary, so the
 * expected percentage strings are equalities and not approximations.
 */

import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { SourceHighlight } from "./SourceHighlight"

/** A stored payload as `Locator.to_json` writes it, US-Letter page. */
function rectanglePayload(): Record<string, unknown> {
  return {
    kind: "page_rectangle",
    page: 3,
    rect: [153000, 198000, 306000, 396000],
    page_size: [612000, 792000],
    units: "millipoints",
    space: "pdf_displayed",
  }
}

const PAGE_IMAGE = "blob:page-3"

describe("SourceHighlight: unreadable payloads", () => {
  it("shows the refusal reason verbatim, never a guessed box", () => {
    render(<SourceHighlight payload={{ kind: "paragraph" }} pageImageUrl={PAGE_IMAGE} />)
    const sentence = screen.getByTestId("locator-unreadable")
    expect(sentence.textContent).toContain("The stored location could not be read")
    expect(sentence.textContent).toContain("not a known locator kind")
    expect(screen.queryByTestId("locator-highlight")).toBeNull()
  })
})

describe("SourceHighlight: sources without pages", () => {
  it("says there is no place to point at", () => {
    render(<SourceHighlight payload={{ kind: "not_positional" }} />)
    expect(screen.getByTestId("locator-not-positional").textContent).toContain(
      "no place on a page to point at",
    )
  })
})

describe("SourceHighlight: capture that was attempted and failed", () => {
  it("without a page, says the place could not be captured", () => {
    render(<SourceHighlight payload={{ kind: "unlocated" }} />)
    expect(screen.getByTestId("locator-unlocated").textContent).toBe(
      "The place this value was read from could not be captured.",
    )
  })

  it("with a page, still gives the page it does know", () => {
    render(<SourceHighlight payload={{ kind: "unlocated", page: 7 }} />)
    expect(screen.getByTestId("locator-unlocated").textContent).toContain("page 7")
    expect(screen.getByTestId("locator-unlocated").textContent).toContain(
      "could not be captured",
    )
  })
})

describe("SourceHighlight: page known, position never captured", () => {
  it("says which page, and why there is no highlight", () => {
    render(<SourceHighlight payload={{ kind: "page_only", page: 12 }} />)
    const sentence = screen.getByTestId("locator-page-only")
    expect(sentence.textContent).toContain("page 12")
    expect(sentence.textContent).toContain("not captured")
    // No image was supplied, so none is rendered.
    expect(screen.queryByRole("img")).toBeNull()
  })

  it("shows the plain page when an image is supplied, with no box on it", () => {
    render(
      <SourceHighlight payload={{ kind: "page_only", page: 12 }} pageImageUrl={PAGE_IMAGE} />,
    )
    const image = screen.getByAltText("Page 12 of the source document")
    expect(image.getAttribute("src")).toBe(PAGE_IMAGE)
    expect(screen.queryByTestId("locator-highlight-box")).toBeNull()
  })
})

describe("SourceHighlight: rectangle recorded", () => {
  it("says so plainly when no page rendering is available to draw on", () => {
    render(<SourceHighlight payload={rectanglePayload()} />)
    const sentence = screen.getByTestId("locator-no-page-image")
    expect(sentence.textContent).toContain("page 3 is recorded")
    expect(screen.queryByTestId("locator-highlight")).toBeNull()
  })

  it("draws the box by fractions of the page", () => {
    // rect [153000, 198000, 306000, 396000] on a 612000x792000 page:
    // x0 = 1/4 of width, x1 = 1/2; y0 = 1/4 of height, y1 = 1/2.
    render(<SourceHighlight payload={rectanglePayload()} pageImageUrl={PAGE_IMAGE} />)
    const box = screen.getByTestId("locator-highlight-box")
    expect(box.style.left).toBe("25%")
    expect(box.style.top).toBe("25%")
    expect(box.style.width).toBe("25%")
    expect(box.style.height).toBe("25%")
  })

  it("renders the full page image underneath the box", () => {
    render(<SourceHighlight payload={rectanglePayload()} pageImageUrl={PAGE_IMAGE} />)
    const image = screen.getByAltText("Page 3 of the source document")
    expect(image.getAttribute("src")).toBe(PAGE_IMAGE)
  })

  it("names the highlighted value in the accessible label when told what it is", () => {
    render(
      <SourceHighlight
        payload={rectanglePayload()}
        pageImageUrl={PAGE_IMAGE}
        valueLabel="the $1,250.00 amount"
      />,
    )
    expect(
      screen.getByLabelText("Highlighted source of the $1,250.00 amount on page 3"),
    ).toBeTruthy()
  })

  it("still labels the region when no value label is given", () => {
    render(<SourceHighlight payload={rectanglePayload()} pageImageUrl={PAGE_IMAGE} />)
    expect(screen.getByLabelText("Highlighted source region on page 3")).toBeTruthy()
  })
})
