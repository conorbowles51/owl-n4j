import { fireEvent, render, screen } from "@testing-library/react"
import { beforeEach, expect, it, vi } from "vitest"
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom"
import { LoginPage } from "./LoginPage"
import { useAuthStore } from "../hooks/use-auth"
const login = vi.hoisted(() => vi.fn())
const loginSecondStep = vi.hoisted(() => vi.fn())
const resetWithCode = vi.hoisted(() => vi.fn())
vi.mock("../api", () => ({ authAPI: { login, loginSecondStep, resetWithCode } }))
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

function signInForm() {
  render(
    <MemoryRouter initialEntries={["/login"]}>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="*" element={<Destination />} />
      </Routes>
    </MemoryRouter>
  )
  fireEvent.change(screen.getByLabelText("Username"), { target: { value: "reader@example.test" } })
  fireEvent.change(screen.getByLabelText("Password"), { target: { value: "a long password" } })
}

it("asks for the code after the password and opens nothing until it is right", async () => {
  login.mockResolvedValue({
    two_step_required: true,
    two_step_token: "pending",
    username: "reader@example.test",
  })
  loginSecondStep.mockRejectedValueOnce(new Error("That code is not right"))
  loginSecondStep.mockResolvedValueOnce({
    access_token: "test-token",
    username: "reader@example.test",
    name: "Reader",
    role: "user",
  })
  signInForm()
  fireEvent.click(screen.getByRole("button", { name: "Sign in" }))
  const code = await screen.findByLabelText("Code from your authenticator app")
  expect(useAuthStore.getState().isAuthenticated).toBe(false)
  fireEvent.change(code, { target: { value: "000000" } })
  fireEvent.click(screen.getByRole("button", { name: "Continue" }))
  expect((await screen.findByRole("alert")).textContent).toContain("not right")
  expect(useAuthStore.getState().isAuthenticated).toBe(false)
  fireEvent.change(code, { target: { value: "123456" } })
  fireEvent.click(screen.getByRole("button", { name: "Continue" }))
  await screen.findByText(/Returned to \/cases/)
  expect(loginSecondStep).toHaveBeenLastCalledWith("pending", "123456")
  expect(useAuthStore.getState().isAuthenticated).toBe(true)
})

it("sends an administrator who must enrol to the security page", async () => {
  login.mockResolvedValue({
    access_token: "test-token",
    username: "reader@example.test",
    name: "Reader",
    role: "admin",
    two_step_setup_required: true,
  })
  signInForm()
  fireEvent.click(screen.getByRole("button", { name: "Sign in" }))
  await screen.findByText(/Returned to \/settings\/security/)
})

it("sets a new password from a reset code and returns to sign-in", async () => {
  resetWithCode.mockResolvedValue(undefined)
  signInForm()
  fireEvent.click(screen.getByRole("button", { name: "I have a reset code" }))
  fireEvent.change(screen.getByLabelText("Reset code"), { target: { value: "AAAA-BBBB" } })
  fireEvent.change(screen.getByLabelText("New password"), { target: { value: "one long password" } })
  fireEvent.change(screen.getByLabelText("New password again"), { target: { value: "another" } })
  fireEvent.click(screen.getByRole("button", { name: "Set new password" }))
  expect((await screen.findByRole("alert")).textContent).toContain("different")
  expect(resetWithCode).not.toHaveBeenCalled()
  fireEvent.change(screen.getByLabelText("New password again"), { target: { value: "one long password" } })
  fireEvent.click(screen.getByRole("button", { name: "Set new password" }))
  expect((await screen.findByRole("status")).textContent).toContain("Password set")
  expect(resetWithCode).toHaveBeenCalledWith("reader@example.test", "AAAA-BBBB", "one long password")
})
