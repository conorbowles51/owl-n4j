import { act, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { TooltipProvider } from "@/components/ui/tooltip"
import { useGraphStore } from "@/stores/graph.store"
import { GraphToolbar } from "./GraphToolbar"

function renderToolbar() {
  return render(
    <TooltipProvider>
      <GraphToolbar caseId="case-1" filteredNodes={3} totalNodes={10} />
    </TooltipProvider>
  )
}

describe("GraphToolbar search", () => {
  beforeEach(() => {
    vi.useFakeTimers()
    useGraphStore.setState({
      searchMode: "filter",
      searchDraft: "",
      appliedSearchQuery: "",
    })
  })

  afterEach(() => vi.useRealTimers())

  it("debounces live filtering and reports result counts", () => {
    renderToolbar()
    fireEvent.change(screen.getByRole("textbox", { name: "Filter graph entities" }), {
      target: { value: "Alice" },
    })
    expect(useGraphStore.getState().appliedSearchQuery).toBe("")
    act(() => vi.advanceTimersByTime(300))
    expect(useGraphStore.getState().appliedSearchQuery).toBe("Alice")
    expect(screen.getByText("3 / 10")).toBeInTheDocument()
  })

  it("only submits fuzzy Search on Enter or button click", () => {
    renderToolbar()
    fireEvent.change(screen.getByRole("combobox", { name: "Graph search mode" }), {
      target: { value: "search" },
    })
    const input = screen.getByRole("textbox", { name: "Search graph entities" })
    fireEvent.change(input, { target: { value: "Alce" } })
    act(() => vi.advanceTimersByTime(500))
    expect(useGraphStore.getState().appliedSearchQuery).toBe("")
    fireEvent.keyDown(input, { key: "Enter" })
    expect(useGraphStore.getState().appliedSearchQuery).toBe("Alce")
  })

  it("clears immediately with Escape and refocuses after the clear button", () => {
    renderToolbar()
    const input = screen.getByRole("textbox", { name: "Filter graph entities" })
    fireEvent.change(input, { target: { value: "Alice" } })
    act(() => vi.advanceTimersByTime(300))
    fireEvent.keyDown(input, { key: "Escape" })
    expect(useGraphStore.getState().searchDraft).toBe("")
    expect(useGraphStore.getState().appliedSearchQuery).toBe("")

    fireEvent.change(input, { target: { value: "Bob" } })
    fireEvent.click(screen.getByRole("button", { name: "Clear graph search" }))
    expect(input).toHaveFocus()
  })

  it("focuses and selects the input with Ctrl+F", () => {
    renderToolbar()
    const input = screen.getByRole("textbox", { name: "Filter graph entities" }) as HTMLInputElement
    fireEvent.change(input, { target: { value: "Alice" } })
    fireEvent.keyDown(window, { key: "f", ctrlKey: true })
    expect(input).toHaveFocus()
    expect(input.selectionStart).toBe(0)
    expect(input.selectionEnd).toBe(5)
  })
})

