import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import { MapToolbar } from "./MapToolbar"

describe("MapToolbar", () => {
  it("does not render the deprecated rescan control", () => {
    render(<MapToolbar locations={[]} />)

    expect(screen.queryByRole("button", { name: /rescan/i })).not.toBeInTheDocument()
    expect(screen.queryByText(/rescan/i)).not.toBeInTheDocument()
  })
})
