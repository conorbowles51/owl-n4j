import { useState } from "react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { act, fireEvent, render, screen } from "@testing-library/react"
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "./dialog"
import { Sheet, SheetContent, SheetDescription, SheetTitle } from "./sheet"
import { DISCARD_TYPED_PROMPT, isTypedField } from "./typed-content-guard"

function DialogHarness({ guard }: { guard?: boolean }) {
  const [open, setOpen] = useState(true)
  return (
    <>
      <div data-testid="outside">page behind</div>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent guardTypedContent={guard}>
          <DialogTitle>New note</DialogTitle>
          <DialogDescription>Write a note</DialogDescription>
          <textarea aria-label="body" />
          <input aria-label="find" placeholder="Search the case" />
          <input aria-label="flag" type="checkbox" />
        </DialogContent>
      </Dialog>
    </>
  )
}

function SheetHarness() {
  const [open, setOpen] = useState(true)
  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetContent>
        <SheetTitle>Edit entry</SheetTitle>
        <SheetDescription>Edit</SheetDescription>
        <input aria-label="title" />
      </SheetContent>
    </Sheet>
  )
}

// Radix registers its outside-pointer listener on the next tick after opening.
async function settle() {
  await act(async () => { await new Promise((r) => setTimeout(r, 20)) })
}

function clickOutside() {
  act(() => {
    fireEvent.pointerDown(document.body, { button: 0, pointerType: "mouse" })
  })
}

function pressEscape() {
  act(() => {
    fireEvent.keyDown(document.activeElement ?? document.body, { key: "Escape" })
  })
}

afterEach(() => vi.restoreAllMocks())

describe("typed content guard (BUG-006: an outside click lost unsaved work)", () => {
  it("keeps a dialog with typed text open on an outside click when the person says no", async () => {
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false)
    render(<DialogHarness />)
    await settle()
    fireEvent.input(screen.getByLabelText("body"), { target: { value: "long note" } })
    clickOutside()
    expect(confirm).toHaveBeenCalledWith(DISCARD_TYPED_PROMPT)
    expect(screen.getByRole("dialog")).toBeTruthy()
    expect((screen.getByLabelText("body") as HTMLTextAreaElement).value).toBe("long note")
  })

  it("keeps it open on Escape too, and closes when the person agrees to discard", async () => {
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false)
    render(<DialogHarness />)
    await settle()
    fireEvent.input(screen.getByLabelText("body"), { target: { value: "long note" } })
    pressEscape()
    expect(screen.getByRole("dialog")).toBeTruthy()
    confirm.mockReturnValue(true)
    clickOutside()
    expect(screen.queryByRole("dialog")).toBeNull()
  })

  it("closes without asking when nothing was typed, or only a search box or checkbox changed", async () => {
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false)
    render(<DialogHarness />)
    await settle()
    fireEvent.input(screen.getByLabelText("find"), { target: { value: "acme" } })
    fireEvent.click(screen.getByLabelText("flag"))
    clickOutside()
    expect(confirm).not.toHaveBeenCalled()
    expect(screen.queryByRole("dialog")).toBeNull()
  })

  it("can be switched off per dialog", async () => {
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false)
    render(<DialogHarness guard={false} />)
    await settle()
    fireEvent.input(screen.getByLabelText("body"), { target: { value: "x" } })
    clickOutside()
    expect(confirm).not.toHaveBeenCalled()
    expect(screen.queryByRole("dialog")).toBeNull()
  })

  it("guards sheets (the casework detail editor) the same way", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(false)
    render(<SheetHarness />)
    await settle()
    fireEvent.input(screen.getByLabelText("title"), { target: { value: "edited" } })
    clickOutside()
    expect(screen.getByRole("dialog")).toBeTruthy()
  })

  it("classifies fields", () => {
    const ta = document.createElement("textarea")
    const cb = document.createElement("input"); cb.type = "checkbox"
    const s = document.createElement("input"); s.type = "search"
    const t = document.createElement("input")
    expect(isTypedField(ta)).toBe(true)
    expect(isTypedField(t)).toBe(true)
    expect(isTypedField(cb)).toBe(false)
    expect(isTypedField(s)).toBe(false)
    expect(isTypedField(null)).toBe(false)
  })
})
