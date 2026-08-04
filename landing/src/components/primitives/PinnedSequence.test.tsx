import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import { PinnedSequence } from "./PinnedSequence"

describe("PinnedSequence", () => {
  it("renders its child with a progress value", () => {
    render(
      <PinnedSequence steps={3} label="test sequence">
        {(progress) => <p>progress: {progress.toFixed(2)}</p>}
      </PinnedSequence>
    )
    expect(screen.getByText(/progress: 0.00/)).toBeInTheDocument()
  })

  it("exposes the label to assistive technology", () => {
    render(
      <PinnedSequence steps={3} label="test sequence">
        {() => <p>content</p>}
      </PinnedSequence>
    )
    expect(screen.getByRole("region", { name: "test sequence" })).toBeInTheDocument()
  })

  it("jumps straight to the final state when forced", () => {
    render(
      <PinnedSequence steps={3} label="test sequence" forceComplete>
        {(progress) => <p>progress: {progress.toFixed(2)}</p>}
      </PinnedSequence>
    )
    expect(screen.getByText(/progress: 1.00/)).toBeInTheDocument()
  })

  it("does not reserve scroll height when complete", () => {
    const { container } = render(
      <PinnedSequence steps={3} label="test sequence" forceComplete>
        {() => <p>content</p>}
      </PinnedSequence>
    )
    const section = container.querySelector("section")!
    expect(section.style.minHeight).toBe("auto")
  })
})
