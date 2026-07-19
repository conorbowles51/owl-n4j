import { render, screen } from "@testing-library/react"
import { Network } from "lucide-react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { SignificantEmptyState } from "./SignificantEmptyState"

const mocks = vi.hoisted(() => ({
  setLayer: vi.fn(),
  useSignificantManifest: vi.fn(),
}))

vi.mock("../hooks/use-significant", () => ({
  useSignificantManifest: mocks.useSignificantManifest,
}))

vi.mock("../stores/case-layer.store", () => ({
  useCaseLayerStore: (
    selector: (state: { setLayer: typeof mocks.setLayer }) => unknown
  ) => selector({ setLayer: mocks.setLayer }),
}))

const props = {
  caseId: "case-1",
  icon: Network,
  eligibleTitle: "Nothing eligible here",
  eligibleDescription: "Marked entities exist, but none belong in this view.",
}

describe("SignificantEmptyState", () => {
  beforeEach(() => {
    mocks.setLayer.mockReset()
    mocks.useSignificantManifest.mockReset()
  })

  it("shows a neutral loading state until the manifest resolves", () => {
    mocks.useSignificantManifest.mockReturnValue({
      data: undefined,
      isPending: true,
    })

    render(<SignificantEmptyState {...props} />)

    expect(
      screen.getByRole("status", { name: "Loading Significant layer" })
    ).toBeInTheDocument()
    expect(
      screen.queryByText("Your Significant layer is empty")
    ).not.toBeInTheDocument()
  })

  it("describes view eligibility after a populated manifest resolves", () => {
    mocks.useSignificantManifest.mockReturnValue({
      data: { count: 4, entity_keys: [] },
      isPending: false,
    })

    render(<SignificantEmptyState {...props} />)

    expect(screen.getByText("Nothing eligible here")).toBeInTheDocument()
    expect(
      screen.getByText("Marked entities exist, but none belong in this view.")
    ).toBeInTheDocument()
  })
})
