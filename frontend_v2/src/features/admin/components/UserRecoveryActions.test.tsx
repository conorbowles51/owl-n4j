import { fireEvent, render, screen } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { beforeEach, expect, it, vi } from "vitest"
import type { User } from "@/features/auth/auth.types"
import { UserRecoveryActions } from "./UserRecoveryActions"

const fetchAPI = vi.hoisted(() => vi.fn())
vi.mock("@/lib/api-client", () => ({ fetchAPI }))

const person: User = { id: "u1", username: "a@example.test", email: "a@example.test", name: "Ann", role: null, global_role: "user" }
const admin: User = { username: "boss@example.test", name: "Boss", role: "admin" }

function row(user: User, currentUser: User, enrolled?: { recovery_codes_left: number }) {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <UserRecoveryActions user={user} currentUser={currentUser} enrolled={enrolled} />
    </QueryClientProvider>
  )
}

beforeEach(() => fetchAPI.mockReset())

it("shows who has enrolled", () => {
  row(person, admin, { recovery_codes_left: 4 })
  screen.getByText("Two-step on")
})

it("issues a reset code after a warning and shows it once", async () => {
  fetchAPI.mockResolvedValue({ code: "AAAA-BBBB-CCCC-DDDD", expires_at: "2026-11-05T12:00:00+00:00" })
  row(person, admin)
  expect(screen.queryByRole("button", { name: "Remove two-step" })).toBeNull()
  fireEvent.click(screen.getByRole("button", { name: "Reset code" }))
  fireEvent.click(await screen.findByRole("button", { name: "Issue code" }))
  expect((await screen.findByLabelText("Reset code")).textContent).toBe("AAAA-BBBB-CCCC-DDDD")
  expect(fetchAPI).toHaveBeenCalledWith("/api/users/u1/reset-code", { method: "POST" })
})

it("offers nothing on your own row, or on an administrator's unless you are a super admin", () => {
  row({ ...admin, id: "u2", email: "boss@example.test" }, admin)
  expect(screen.queryByRole("button", { name: "Reset code" })).toBeNull()
  row({ ...person, id: "u3", global_role: "admin" }, admin)
  expect(screen.queryByRole("button", { name: "Reset code" })).toBeNull()
  row({ ...person, id: "u3", global_role: "admin" }, { ...admin, role: "super_admin" })
  screen.getByRole("button", { name: "Reset code" })
})
