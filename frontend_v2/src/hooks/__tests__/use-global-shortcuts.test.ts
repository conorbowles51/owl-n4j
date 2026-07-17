import { cleanup, render } from "@testing-library/react"
import { createElement } from "react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { useGlobalShortcuts } from "../use-global-shortcuts"

const mocks = vi.hoisted(() => ({
  navigate: vi.fn(),
}))

vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>()

  return {
    ...actual,
    useNavigate: () => mocks.navigate,
    useParams: () => ({ id: "case-1" }),
  }
})

function GlobalShortcutHarness() {
  useGlobalShortcuts()

  return null
}

describe("useGlobalShortcuts", () => {
  afterEach(() => {
    cleanup()
    mocks.navigate.mockClear()
  })

  it("navigates with the shifted case-view shortcut", () => {
    render(createElement(GlobalShortcutHarness))

    const event = new KeyboardEvent("keydown", {
      key: "@",
      code: "Digit2",
      ctrlKey: true,
      shiftKey: true,
      bubbles: true,
      cancelable: true,
    })
    document.dispatchEvent(event)

    expect(mocks.navigate).toHaveBeenCalledWith("/cases/case-1/timeline")
    expect(event.defaultPrevented).toBe(true)
  })

  it("does not hijack the browser search shortcut", () => {
    render(createElement(GlobalShortcutHarness))

    const event = new KeyboardEvent("keydown", {
      key: "k",
      code: "KeyK",
      ctrlKey: true,
      bubbles: true,
      cancelable: true,
    })
    document.dispatchEvent(event)

    expect(mocks.navigate).not.toHaveBeenCalled()
    expect(event.defaultPrevented).toBe(false)
  })
})
