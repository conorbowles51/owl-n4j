import { fireEvent, render, screen } from "@testing-library/react"
import { beforeEach, expect, it, vi } from "vitest"
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom"
import { LoginPage } from "./LoginPage"
import { useAuthStore } from "../hooks/use-auth"
const login = vi.hoisted(() => vi.fn())
vi.mock("../api", () => ({ authAPI: { login } }))
beforeEach(() => {
  login.mockResolvedValue({
    access_token: "test-token",
    username: "reader@example.test",
    name: "Reader",
    role: "user",
  })
  useAuthStore.setState({ isAuthenticated: false, user: null })
  localStorage.clear()
})
function Destination() {
  const location = useLocation()
  return (
    <p>
      Returned to {location.pathname}
      {location.search}
      {location.hash}
    </p>
  )
}
it.each([
  [
    {
      pathname: "/cases/example/financial",
      search: "?account=one",
      hash: "#source",
    },
    "/cases/example/financial?account=one#source",
  ],
  [undefined, "/cases"],
  [{ pathname: "//outside.example/" }, "/cases"],
  [{ pathname: "/\\outside.example/" }, "/cases"],
  [{ pathname: "/login" }, "/cases"],
])(
  "returns to an internal case after login and refuses an invalid destination (%j)",
  async (from, expected) => {
    render(
      <MemoryRouter initialEntries={[{ pathname: "/login", state: { from } }]}>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="*" element={<Destination />} />
        </Routes>
      </MemoryRouter>
    )
    fireEvent.change(screen.getByPlaceholderText("Enter your username"), {
      target: { value: "reader@example.test" },
    })
    fireEvent.change(screen.getByPlaceholderText("Enter your password"), {
      target: { value: "synthetic-password" },
    })
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }))
    expect(await screen.findByText(`Returned to ${expected}`)).toBeVisible()
  }
)
