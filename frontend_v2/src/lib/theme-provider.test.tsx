import { render, screen } from "@testing-library/react"
import { afterEach, expect, it, vi } from "vitest"
import { ThemeProvider } from "./theme-provider"

afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

it("shows the page in the default theme when the browser refuses site storage", () => {
  const refused = () => {
    throw new DOMException("The operation is insecure.", "SecurityError")
  }
  vi.stubGlobal("matchMedia", () => ({ matches: true, addEventListener() {}, removeEventListener() {} }))
  vi.spyOn(Storage.prototype, "getItem").mockImplementation(refused)
  vi.spyOn(Storage.prototype, "setItem").mockImplementation(refused)
  render(
    <ThemeProvider>
      <p>Loupe</p>
    </ThemeProvider>
  )
  expect(screen.getByText("Loupe")).toBeTruthy()
  expect(document.documentElement.classList.contains("dark")).toBe(true)
})
