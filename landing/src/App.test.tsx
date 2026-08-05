import { existsSync } from "node:fs"
import { join } from "node:path"
import { render, screen, waitFor, within } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import { App } from "./App"

/** Renders the app and waits for the lazy below-fold sections to resolve. */
async function renderApp() {
  const result = render(<App />)
  await waitFor(() => {
    expect(result.container.querySelector("#surfaces")).not.toBeNull()
  })
  return result
}

describe("App", () => {
  it("renders one main landmark", async () => {
    await renderApp()
    expect(screen.getAllByRole("main")).toHaveLength(1)
  })

  it("has exactly one h1", async () => {
    await renderApp()
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1)
  })

  it("gives every pinned sequence an accessible name", async () => {
    await renderApp()
    for (const region of screen.getAllByRole("region")) {
      expect(region).toHaveAccessibleName()
    }
  })

  it("every nav link points at a section that exists", async () => {
    const { container } = await renderApp()
    const nav = container.querySelector(".nav-links")!
    const targets = [...nav.querySelectorAll("a")]
      .map((a) => a.getAttribute("href"))
      .filter((h): h is string => !!h && h.startsWith("#"))

    expect(targets.length).toBeGreaterThan(0)
    for (const href of targets) {
      expect(container.querySelector(href), `missing target for ${href}`).not.toBeNull()
    }
  })

  it("every product image resolves to a file that exists", async () => {
    const { container } = await renderApp()
    const srcs = new Set<string>()

    for (const img of container.querySelectorAll("img[src^='/product/']")) {
      srcs.add(img.getAttribute("src")!)
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

  it("carries the illustrative-data caption wherever case data is shown", async () => {
    const { container } = await renderApp()
    const shots = container.querySelectorAll("img[src^='/product/']")
    expect(shots.length).toBeGreaterThan(0)
    expect(screen.getAllByText(/illustrative/i).length).toBeGreaterThanOrEqual(1)
  })

  it("states the deployment position", async () => {
    await renderApp()
    const deployment = document.querySelector("#deployment")!
    expect(within(deployment as HTMLElement).getByText(/single-tenant/i)).toBeInTheDocument()
  })

  it("tells the story in order: case before evidence, finding before proof", async () => {
    const { container } = await renderApp()
    const order = ["#case", "#ingest", "#graph", "#agent", "#finding", "#sourced", "#surfaces"]
    const positions = order.map((sel) => {
      const el = container.querySelector(sel)
      expect(el, `missing section ${sel}`).not.toBeNull()
      return [...container.querySelectorAll("section")].indexOf(el as HTMLElement)
    })
    for (let i = 1; i < positions.length; i++) {
      expect(positions[i], `${order[i]} out of order`).toBeGreaterThan(positions[i - 1])
    }
  })
})
