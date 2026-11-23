import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { fireEvent, render, screen } from "@testing-library/react"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { CorroborateTray } from "./CorroborateTray"
import { addPart } from "./selection-store"

// At 390 px the floating tray covered the bottom ~120 px of every page, the agent's message box included (live
// 2ae9b6ca, 23 Nov). Below md it is a one-line strip in the page's flow, so the page ends above it.
function phoneWidth(narrow: boolean) {
  vi.stubGlobal("matchMedia", (query: string) => ({
    matches: narrow && query === "(max-width: 767px)", media: query,
    addEventListener: () => {}, removeEventListener: () => {},
  }))
}

function wrap() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={qc}><MemoryRouter initialEntries={["/cases/c1/ledger"]}>
    <Routes><Route path="/cases/:id/ledger" element={<CorroborateTray />} /></Routes>
  </MemoryRouter></QueryClientProvider>)
}

const part = { screen: "Dossiers", label: "Mateo Ruiz", members: [{ type: "person", id: "p1", label: "Mateo Ruiz" }], skipped: [] }

beforeEach(() => { localStorage.clear() })
afterEach(() => { vi.unstubAllGlobals() })

describe("the Corroborate tray at phone width", () => {
  it("is a one-line strip in the page's flow, not a box floating over the page", () => {
    phoneWidth(true)
    addPart("c1", part)
    wrap()
    const tray = screen.getByRole("region", { name: "Corroborate selection" })
    expect(tray.className).not.toMatch(/\bfixed\b/)
    expect(tray.className).toMatch(/\bh-10\b/)
    expect(tray.className).toMatch(/\bshrink-0\b/)
    expect(screen.getByText("1 item selected")).toBeTruthy()
    expect(screen.getByRole("button", { name: "Corroborate" })).toBeTruthy()
    // The chips and the other actions wait behind More.
    expect(screen.queryByText("Mateo Ruiz")).toBeNull()
    fireEvent.click(screen.getByRole("button", { name: "More" }))
    expect(screen.getByText("Mateo Ruiz")).toBeTruthy()
    expect(screen.getByRole("button", { name: "Save or combine" })).toBeTruthy()
    expect(screen.getByRole("button", { name: "Less" }).getAttribute("aria-expanded")).toBe("true")
  })

  it("with nothing selected keeps its three ways in, in the same strip", () => {
    phoneWidth(true)
    wrap()
    const tray = screen.getByRole("region", { name: "Corroborate selection" })
    expect(tray.className).not.toMatch(/\bfixed\b/)
    for (const name of ["Paste a list", "Saved subsets", "Check a claim"]) expect(screen.getByRole("button", { name })).toBeTruthy()
  })

  it("stays the floating tray from md up", () => {
    phoneWidth(false)
    addPart("c1", part)
    wrap()
    expect(screen.getByRole("region", { name: "Corroborate selection" }).className).toMatch(/\bfixed\b/)
    expect(screen.getByText("Mateo Ruiz")).toBeTruthy()
  })
})
