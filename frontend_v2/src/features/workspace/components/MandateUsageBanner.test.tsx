import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import { MandateUsageBanner } from "./MandateUsageBanner"

describe("MandateUsageBanner", () => {
  it("identifies the anchored version and adopts a newer active version explicitly", async () => {
    const onAdoptCurrent = vi.fn().mockResolvedValue(undefined)
    render(
      <MandateUsageBanner
        versionNumber={2}
        activeVersionNumber={3}
        stale
        temporaryOverride=""
        onTemporaryOverrideChange={vi.fn()}
        onAdoptCurrent={onAdoptCurrent}
      />,
    )

    expect(screen.getByText("Using case mandate")).toBeInTheDocument()
    expect(screen.getByText("v2")).toBeInTheDocument()
    expect(screen.getByText(/newer version \(v3\)/i)).toBeInTheDocument()

    fireEvent.click(screen.getByRole("button", { name: /adopt current/i }))
    await waitFor(() => expect(onAdoptCurrent).toHaveBeenCalledTimes(1))
  })

  it("edits a request-only override without changing saved mandate state", () => {
    const onTemporaryOverrideChange = vi.fn()
    const { rerender } = render(
      <MandateUsageBanner
        versionNumber={4}
        temporaryOverride=""
        onTemporaryOverrideChange={onTemporaryOverrideChange}
      />,
    )

    fireEvent.click(
      screen.getByRole("button", { name: /override for next request/i }),
    )
    fireEvent.change(screen.getByLabelText("Temporary mandate override"), {
      target: { value: "Test the contrary explanation" },
    })
    expect(onTemporaryOverrideChange).toHaveBeenCalledWith(
      "Test the contrary explanation",
    )

    rerender(
      <MandateUsageBanner
        versionNumber={4}
        temporaryOverride="Test the contrary explanation"
        onTemporaryOverrideChange={onTemporaryOverrideChange}
      />,
    )
    expect(screen.getByText("Request override")).toBeInTheDocument()
    expect(screen.getByText(/cleared after the request is sent/i)).toBeInTheDocument()
  })

  it("makes an incomplete mandate explicit", () => {
    render(
      <MandateUsageBanner
        incomplete
        temporaryOverride=""
        onTemporaryOverrideChange={vi.fn()}
      />,
    )

    expect(screen.getByText("No saved case mandate")).toBeInTheDocument()
  })
})
