import { existsSync } from "node:fs"
import { join } from "node:path"
import { render, screen, within } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import { App } from "./App"

describe("App", () => {
  it("renders one main landmark", () => {
    render(<App />)
    expect(screen.getAllByRole("main")).toHaveLength(1)
  })

  it("has exactly one h1", () => {
    render(<App />)
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1)
  })

  it("gives every pinned sequence an accessible name", () => {
    render(<App />)
    for (const region of screen.getAllByRole("region")) {
      expect(region).toHaveAccessibleName()
    }
  })

  it("every nav link points at a section that exists", () => {
    const { container } = render(<App />)
    const nav = container.querySelector(".nav-links")!
    const targets = [...nav.querySelectorAll("a")]
      .map((a) => a.getAttribute("href"))
      .filter((h): h is string => !!h && h.startsWith("#"))

    expect(targets.length).toBeGreaterThan(0)
    for (const href of targets) {
      expect(container.querySelector(href), `missing target for ${href}`).not.toBeNull()
    }
  })

  it("every product image resolves to a file that exists", () => {
    const { container } = render(<App />)
    const srcs = new Set<string>()

    for (const img of container.querySelectorAll("img[src^='/product/']")) {
      srcs.add(img.getAttribute("src")!)
      // srcset carries the 1280 variant, which is just as easy to typo.
      for (const candidate of (img.getAttribute("srcset") ?? "").split(",")) {
        const url = candidate.trim().split(/\s+/)[0]
        if (url.startsWith("/product/")) srcs.add(url)
      }
    }

    expect(srcs.size).toBeGreaterThan(0)
    for (const src of srcs) {
      expect(existsSync(join("public", src)), `missing asset ${src}`).toBe(true)
    }
  })

  it("carries the illustrative-data caption wherever case data is shown", () => {
    const { container } = render(<App />)
    const shots = container.querySelectorAll("img[src^='/product/']")
    expect(shots.length).toBeGreaterThan(0)
    expect(screen.getAllByText(/illustrative/i).length).toBeGreaterThanOrEqual(1)
  })

  it("states the deployment position", () => {
    render(<App />)
    const trust = document.querySelector("#trust")!
    expect(within(trust as HTMLElement).getByText(/single-tenant/i)).toBeInTheDocument()
  })
})
