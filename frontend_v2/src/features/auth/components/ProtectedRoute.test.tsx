import { act, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { beforeEach, expect, it, vi } from "vitest"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { ProtectedRoute } from "./ProtectedRoute"
import { useAuthStore } from "../hooks/use-auth"
import type { User } from "../auth.types"
import { ApiError } from "@/lib/api-client"
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

it("keeps a valid token after a server failure and confirms the profile on retry", async () => {
  me.mockRejectedValueOnce(
    new ApiError("Temporarily unavailable", 503)
  ).mockResolvedValueOnce(user)
  mount()
  expect(
    await screen.findByRole("heading", { name: "Cannot check sign-in" })
  ).toBeVisible()
  expect(localStorage.getItem("authToken")).toBe("old-token")
  expect(screen.queryByText("Private case")).not.toBeInTheDocument()
  expect(screen.queryByText("Login form")).not.toBeInTheDocument()
  expect(me).toHaveBeenCalledTimes(1)
  fireEvent.click(screen.getByRole("button", { name: "Retry connection" }))
  expect(await screen.findByText("Private case")).toBeVisible()
  expect(me).toHaveBeenCalledTimes(2)
})

it("offers explicit sign-in after a network failure without signing out automatically", async () => {
  me.mockRejectedValue(new TypeError("Failed to fetch"))
  mount()
  await screen.findByRole("alert")
  expect(localStorage.getItem("authToken")).toBe("old-token")
  fireEvent.click(screen.getByRole("button", { name: "Sign in again" }))
  expect(await screen.findByText("Login form")).toBeVisible()
  expect(localStorage.getItem("authToken")).toBeNull()
})

it.each([401, 403])(
  "still requires sign-in when the profile is refused with %s",
  async (status) => {
    me.mockRejectedValue(new ApiError("Sign-in refused", status))
    mount()
    expect(await screen.findByText("Login form")).toBeVisible()
    expect(localStorage.getItem("authToken")).toBeNull()
  }
)

it("does not clear a newer login when the old profile request fails", async () => {
  let reject!: (reason: unknown) => void
  me.mockImplementation(
    () =>
      new Promise((_resolve, fail) => {
        reject = fail
      })
  )
  mount()
  await waitFor(() => expect(me).toHaveBeenCalled())
  act(() =>
    useAuthStore
      .getState()
      .login("new-token", { ...user, username: "second@example.test" })
  )
  await act(async () => reject(new ApiError("Expired old token", 401)))
  expect(localStorage.getItem("authToken")).toBe("new-token")
  expect(useAuthStore.getState().user?.username).toBe("second@example.test")
  expect(screen.getByText("Private case")).toBeVisible()
})
