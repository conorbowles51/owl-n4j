import { act, fireEvent, render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import { X } from "lucide-react"
import { Button } from "./button"
import { hasWords } from "./has-words"

/** lx-guidecover C: an icon-only button says what it does on hover and on keyboard focus; a disabled one says why. */
describe("Button tooltips", () => {
  it("an icon-only button shows its name as a tooltip on keyboard focus, and drops the hover-only title", async () => {
    render(<Button size="icon" title="Close the panel"><X /></Button>)
    const button = screen.getByRole("button", { name: "Close the panel" })
    expect(button.getAttribute("title")).toBeNull()
    await act(async () => void fireEvent.focus(button))
    expect((await screen.findAllByText("Close the panel")).length).toBeGreaterThan(0)
  })

  it("a button with words gets no tooltip of its own", async () => {
    render(<Button aria-label="Save the note">Save</Button>)
    const button = screen.getByRole("button", { name: "Save the note" })
    await act(async () => void fireEvent.focus(button))
    expect(screen.queryByRole("tooltip")).toBeNull()
  })

  it("a disabled button with a reason can be reached by keyboard and says why", async () => {
    render(<Button disabled disabledReason="Choose a file first.">Process</Button>)
    const holder = screen.getByLabelText("Choose a file first.")
    expect(holder.tabIndex).toBe(0)
    await act(async () => void fireEvent.focus(holder))
    expect(screen.getAllByText("Choose a file first.").length).toBeGreaterThan(0)
  })

  it("counts words, not icons or hidden labels", () => {
    expect(hasWords(<X />)).toBe(false)
    expect(hasWords(<span className="sr-only">Close</span>)).toBe(false)
    expect(hasWords(["Save", <X key="x" />])).toBe(true)
    expect(hasWords(3)).toBe(true)
  })
})

describe("Button keeps one element across renders", () => {
  it("a button given a reason is the same element when it turns enabled", async () => {
    const { rerender } = render(<Button disabled disabledReason="Choose a file first.">Process</Button>)
    const before = screen.getByRole("button", { name: "Process" })
    expect(before).toBeDisabled()
    rerender(<Button disabled={false} disabledReason={undefined}>Process</Button>)
    expect(screen.getByRole("button", { name: "Process" })).toBe(before)
    expect(before).toBeEnabled()
  })

  it("a named button whose words become a spinner stays the same element", () => {
    const { rerender } = render(<Button aria-label="Save the note">Save</Button>)
    const before = screen.getByRole("button", { name: "Save the note" })
    rerender(<Button aria-label="Save the note"><X /></Button>)
    expect(screen.getByRole("button", { name: "Save the note" })).toBe(before)
  })
})
