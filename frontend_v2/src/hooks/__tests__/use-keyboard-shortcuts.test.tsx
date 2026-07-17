import { render } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import { useKeyboardShortcuts } from "../use-keyboard-shortcuts"

function ShortcutHarness({
  handler,
}: {
  handler: () => void
}) {
  useKeyboardShortcuts([
    {
      key: "1",
      code: "Digit1",
      meta: true,
      shift: true,
      handler,
    },
  ])

  return null
}

describe("useKeyboardShortcuts", () => {
  it("matches shifted digit shortcuts by physical key code", () => {
    const handler = vi.fn()
    render(<ShortcutHarness handler={handler} />)

    const event = new KeyboardEvent("keydown", {
      key: "!",
      code: "Digit1",
      ctrlKey: true,
      shiftKey: true,
      bubbles: true,
      cancelable: true,
    })

    document.dispatchEvent(event)

    expect(handler).toHaveBeenCalledTimes(1)
    expect(event.defaultPrevented).toBe(true)
  })

  it("does not match the unshifted browser tab-switch chord", () => {
    const handler = vi.fn()
    render(<ShortcutHarness handler={handler} />)

    const event = new KeyboardEvent("keydown", {
      key: "1",
      code: "Digit1",
      ctrlKey: true,
      bubbles: true,
      cancelable: true,
    })

    document.dispatchEvent(event)

    expect(handler).not.toHaveBeenCalled()
    expect(event.defaultPrevented).toBe(false)
  })
})
