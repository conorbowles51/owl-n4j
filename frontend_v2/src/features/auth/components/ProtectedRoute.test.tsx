import { act, render, screen, waitFor } from "@testing-library/react"
import { beforeEach, expect, it, vi } from "vitest"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { ProtectedRoute } from "./ProtectedRoute"
import { useAuthStore } from "../hooks/use-auth"
import type { User } from "../auth.types"
const me = vi.hoisted(() => vi.fn())
vi.mock("../api", () => ({ authAPI: { me } }))
const user = { username: "first@example.test", name: "First", role: "user" }
beforeEach(() => {
  me.mockReset()
  localStorage.setItem("authToken", "old-token")
  useAuthStore.setState({ isAuthenticated: true, user: null })
})
function mount() {
  return render(
    <MemoryRouter initialEntries={["/private"]}>
      <Routes>
        <Route element={<ProtectedRoute />}>
          <Route path="/private" element={<p>Private case</p>} />
        </Route>
        <Route path="/login" element={<p>Login form</p>} />
      </Routes>
    </MemoryRouter>
  )
}
it("returns to login when profile loading expires, including after the API removes the token", async () => {
  me.mockImplementation(async () => {
    localStorage.removeItem("authToken")
    throw Error("Expired")
  })
  mount()
  expect(await screen.findByText("Login form")).toBeInTheDocument()
  expect(useAuthStore.getState().isAuthenticated).toBe(false)
})
it("shows the protected page after a current profile arrives", async () => {
  me.mockResolvedValue(user)
  mount()
  expect(await screen.findByText("Private case")).toBeInTheDocument()
})
it("does not replace a newer login with an old in-flight profile response", async () => {
  let resolve!: (value: User) => void
  me.mockImplementation(
    () =>
      new Promise((r) => {
        resolve = r
      })
  )
  mount()
  await waitFor(() => expect(me).toHaveBeenCalled())
  act(() =>
    useAuthStore
      .getState()
      .login("new-token", { ...user, username: "second@example.test" })
  )
  await act(async () => resolve(user))
  expect(useAuthStore.getState().user?.username).toBe("second@example.test")
  expect(await screen.findByText("Private case")).toBeInTheDocument()
})
