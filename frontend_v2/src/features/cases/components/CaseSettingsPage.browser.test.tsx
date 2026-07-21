import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"
import type { Case } from "@/types/case.types"
import { CaseSettingsPage } from "./CaseSettingsPage"

const browserHooks = vi.hoisted(() => ({
  useCase: vi.fn(),
  update: vi.fn(),
}))

vi.mock("../hooks/use-cases", () => ({
  useCase: browserHooks.useCase,
  useUpdateCase: () => ({
    mutateAsync: browserHooks.update,
    isPending: false,
  }),
}))

const storyCase: Case = {
  id: "case-browser-fixture",
  title: "Operation Lantern",
  description: "Initial case description",
  status: "active",
  created_by_user_id: "user-1",
  owner_user_id: "user-1",
  created_at: "2026-07-01T09:00:00Z",
  updated_at: "2026-07-16T10:30:00Z",
  owner_name: "Alex Morgan",
  user_role: "owner",
  is_owner: true,
  archived: false,
  next_deadline_date: null,
  next_deadline_name: null,
}

describe("Case settings in Chromium", () => {
  beforeEach(() => {
    browserHooks.useCase.mockReset()
    browserHooks.update.mockReset()
    browserHooks.useCase.mockReturnValue({
      data: storyCase,
      isLoading: false,
      isError: false,
    })
    browserHooks.update.mockResolvedValue({
      ...storyCase,
      title: "Operation Beacon",
      description: null,
      status: "on_hold",
    })
  })

  it("edits and saves every visible metadata field", async () => {
    render(
      <MemoryRouter initialEntries={["/cases/case-browser-fixture/settings"]}>
        <Routes>
          <Route path="/cases/:id/settings" element={<CaseSettingsPage />} />
        </Routes>
      </MemoryRouter>
    )

    const title = screen.getByLabelText("Case title")
    fireEvent.change(title, { target: { value: "Temporary title" } })
    fireEvent.click(screen.getByRole("button", { name: "Reset" }))
    expect(title).toHaveValue("Operation Lantern")

    fireEvent.change(title, {
      target: { value: "Operation Beacon" },
    })
    fireEvent.change(screen.getByLabelText("Description"), {
      target: { value: "" },
    })
    fireEvent.change(screen.getByLabelText("Case status"), {
      target: { value: "on_hold" },
    })
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }))

    await waitFor(() =>
      expect(browserHooks.update).toHaveBeenCalledWith({
        title: "Operation Beacon",
        description: null,
        status: "on_hold",
      })
    )
    expect(await screen.findByRole("status")).toHaveTextContent(
      "Case details saved"
    )
  })

  it("prevents a viewer from changing case metadata", () => {
    browserHooks.useCase.mockReturnValue({
      data: { ...storyCase, user_role: "viewer", is_owner: false },
      isLoading: false,
      isError: false,
    })

    render(
      <MemoryRouter initialEntries={["/cases/case-browser-fixture/settings"]}>
        <Routes>
          <Route path="/cases/:id/settings" element={<CaseSettingsPage />} />
        </Routes>
      </MemoryRouter>
    )

    expect(screen.getByText("You have view-only access")).toBeInTheDocument()
    expect(screen.getByLabelText("Case title")).toBeDisabled()
    expect(screen.getByLabelText("Description")).toBeDisabled()
    expect(screen.getByLabelText("Case status")).toBeDisabled()
    expect(
      screen.queryByRole("button", { name: "Save changes" })
    ).not.toBeInTheDocument()
  })

  it("preserves entered values and explains a failed save", async () => {
    browserHooks.update.mockRejectedValue(new Error("Service unavailable"))

    render(
      <MemoryRouter initialEntries={["/cases/case-browser-fixture/settings"]}>
        <Routes>
          <Route path="/cases/:id/settings" element={<CaseSettingsPage />} />
        </Routes>
      </MemoryRouter>
    )

    const title = screen.getByLabelText("Case title")
    fireEvent.change(title, { target: { value: "Unsaved title" } })
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }))

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Service unavailable"
    )
    expect(title).toHaveValue("Unsaved title")
  })
})
