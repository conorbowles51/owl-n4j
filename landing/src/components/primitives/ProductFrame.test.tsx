import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import { ProductFrame } from "./ProductFrame"

describe("ProductFrame", () => {
  const base = {
    slug: "graph-detail",
    alt: "Loupe graph view with the entity detail panel open",
    callouts: [{ x: 70, y: 40, text: "Every sentence cites its source file and page" }],
  }

  it("renders a responsive image with both widths", () => {
    render(<ProductFrame {...base} />)
    const img = screen.getByAltText(base.alt)
    expect(img.getAttribute("srcset")).toContain("/product/graph-detail-light@1280.webp 1280w")
    expect(img.getAttribute("srcset")).toContain("/product/graph-detail-light.webp 2560w")
  })

  it("selects the theme variant", () => {
    render(<ProductFrame {...base} theme="dark" />)
    expect(screen.getByAltText(base.alt)).toHaveAttribute(
      "src",
      "/product/graph-detail-dark.webp"
    )
  })

  it("renders each callout", () => {
    render(<ProductFrame {...base} />)
    expect(
      screen.getByText("Every sentence cites its source file and page")
    ).toBeInTheDocument()
  })

  it("always carries the illustrative-data caption", () => {
    render(<ProductFrame {...base} />)
    expect(screen.getByText(/Illustrative case data/i)).toBeInTheDocument()
  })

  it("lazy-loads by default and eager-loads when asked", () => {
    const { rerender } = render(<ProductFrame {...base} />)
    expect(screen.getByAltText(base.alt)).toHaveAttribute("loading", "lazy")
    rerender(<ProductFrame {...base} priority />)
    expect(screen.getByAltText(base.alt)).toHaveAttribute("loading", "eager")
  })

  it("reserves aspect ratio so lazy loading cannot shift layout", () => {
    render(<ProductFrame {...base} />)
    const img = screen.getByAltText(base.alt)
    expect(img).toHaveAttribute("width", "2560")
    expect(img).toHaveAttribute("height", "1440")
  })
})
