import { existsSync } from "node:fs"
import { join } from "node:path"
import { render, screen, within } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import { App } from "./App"

function renderApp() {
  return render(<App />)
}

describe("App", () => {
  it("renders one main landmark and one page heading", () => {
    renderApp()
    expect(screen.getAllByRole("main")).toHaveLength(1)
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1)
  })

  it("points every primary navigation link at an existing section", () => {
    const { container } = renderApp()
    const nav = container.querySelector(".nav-links")!
    const targets = [...nav.querySelectorAll("a")]
      .map((anchor) => anchor.getAttribute("href"))
      .filter((href): href is string => Boolean(href?.startsWith("#")))

    expect(targets.length).toBeGreaterThan(0)
    for (const href of targets) {
      expect(container.querySelector(href), `missing target for ${href}`).not.toBeNull()
    }
  })

  it("ships every referenced film and poster", () => {
    renderApp()
    const assets = [
      "/films/loupe-product-film-poster.webp",
      "/films/loupe-product-film-web.mp4",
      "/films/loupe-product-film-web.webm",
      "/films/evidence-workflow-poster.webp",
      "/films/evidence-workflow.mp4",
      "/films/evidence-workflow.webm",
      "/films/evidence-intelligence-poster.webp",
      "/films/evidence-intelligence.mp4",
      "/films/evidence-intelligence.webm",
      "/films/case-text-search-poster.webp",
      "/films/case-text-search.mp4",
      "/films/case-text-search.webm",
      "/films/case-views-poster.webp",
      "/films/case-views.mp4",
      "/films/case-views.webm",
      "/films/ai-workspace-poster.webp",
      "/films/ai-workspace.mp4",
      "/films/ai-workspace.webm",
    ]

    for (const asset of assets) {
      expect(existsSync(join("public", asset)), `missing asset ${asset}`).toBe(true)
    }
  })

  it("keeps the product film first and the feature story in order", () => {
    const { container } = renderApp()
    const order = ["#film", "#evidence", "#views", "#ai", "#deployment", "#providers"]
    const sections = [...container.querySelectorAll("section")]
    const positions = order.map((selector) => {
      const section = container.querySelector(selector)
      expect(section, `missing section ${selector}`).not.toBeNull()
      return sections.indexOf(section as HTMLElement)
    })

    for (let index = 1; index < positions.length; index += 1) {
      expect(positions[index]).toBeGreaterThan(positions[index - 1])
    }
  })

  it("states the dedicated deployment and provider-choice position", () => {
    renderApp()
    const deployment = document.querySelector("#deployment")!
    expect(within(deployment as HTMLElement).getByText(/dedicated Loupe application instance/i)).toBeInTheDocument()
    expect(within(deployment as HTMLElement).getAllByText(/on-premises/i)).toHaveLength(2)
    expect(within(deployment as HTMLElement).getByText(/your provider, your choice/i)).toBeInTheDocument()

    const providers = document.querySelector("#providers")!
    expect(within(providers as HTMLElement).getByText(/supported out of the box/i)).toBeInTheDocument()
    for (const name of ["OpenAI", "Anthropic", "Gemini", "DeepSeek"]) {
      expect(within(providers as HTMLElement).getByRole("heading", { name })).toBeInTheDocument()
    }
  })
})
