import { renderHook } from "@testing-library/react"
import { afterEach, expect, it, vi } from "vitest"
import type { StreamItem } from "./use-filtered-events"
import { useKeyboardNavigation } from "./use-keyboard-navigation"

const items: StreamItem[] = [
  { kind: "header", date: "2021-02-08", label: "Mon, Feb 8, 2021", count: 2 },
  ...["a", "b"].map((key) => ({
    kind: "event" as const,
    event: {
      key,
      name: key,
      type: "Transaction",
      date: "2021-02-08",
      time: null,
      amount: null,
      summary: null,
      notes: null,
      connections: [],
    },
  })),
]

function setup(selectedEventKey: string | null = null) {
  const params = {
    items,
    selectedEventKey,
    onSelectEvent: vi.fn(),
    onClearSelection: vi.fn(),
    onPrevCluster: vi.fn(),
    onNextCluster: vi.fn(),
    onToggleFilterSidebar: vi.fn(),
    searchInputRef: { current: null },
    scrollToEvent: vi.fn(),
  }
  renderHook(() => useKeyboardNavigation(params))
  return params
}

const press = (target: Element, key: string) => {
  const event = new KeyboardEvent("keydown", { key, bubbles: true, cancelable: true })
  target.dispatchEvent(event)
  return event
}

afterEach(() => {
  document.body.innerHTML = ""
})

it("moves through the Timeline with keys pressed on the page", () => {
  const params = setup()
  press(document.body, "j")
  expect(params.onSelectEvent).toHaveBeenCalledWith("a")
  press(document.body, "Escape")
  expect(params.onClearSelection).toHaveBeenCalled()
})

it("leaves keys pressed inside a dialog or sheet to that dialog", () => {
  const params = setup("a")
  const dialog = document.createElement("div")
  dialog.setAttribute("role", "dialog")
  const button = document.createElement("button")
  dialog.append(button)
  document.body.append(dialog)
  for (const key of ["j", "ArrowDown", "Escape", "[", "/"]) press(button, key)
  // Enter on a dialog's button is not swallowed while an event is selected.
  expect(press(button, "Enter").defaultPrevented).toBe(false)
  expect(params.onSelectEvent).not.toHaveBeenCalled()
  expect(params.onClearSelection).not.toHaveBeenCalled()
  expect(params.onToggleFilterSidebar).not.toHaveBeenCalled()
})
