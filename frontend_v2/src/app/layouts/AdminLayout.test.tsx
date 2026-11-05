import { render, screen } from "@testing-library/react"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { afterEach, describe, expect, it } from "vitest"
import { useAuthStore } from "@/features/auth/hooks/use-auth"
import { AdminLayout } from "./AdminLayout"

function show(role: string | null) {
  useAuthStore.setState({ isAuthenticated: true, user: { username: "a", name: "A", role } })
  return render(
    <MemoryRouter initialEntries={["/admin/users"]}>
      <Routes>
        <Route path="/admin" element={<AdminLayout />}>
          <Route path="users" element={<p>Secret admin content</p>} />
        </Route>
      </Routes>
    </MemoryRouter>
  )
}

afterEach(() => useAuthStore.setState({ isAuthenticated: false, user: null }))

describe("AdminLayout", () => {
  it.each(["user", "guest", null])("refuses %s on the first paint, with no admin content", (role) => {
    const { container } = show(role)
    expect(screen.getByRole("heading", { name: "Administrators only" })).toBeTruthy()
    expect(container.textContent).not.toContain("Secret admin content")
    expect(container.textContent).not.toContain("Administration")
  })

  it.each(["admin", "super_admin"])("opens for %s", (role) => {
    show(role)
    expect(screen.getByText("Secret admin content")).toBeTruthy()
    expect(screen.queryByText("Administrators only")).toBeNull()
  })
})
