import { beforeEach, expect, it } from "vitest"
import { queryClient } from "@/lib/query-client"
import { useAuthStore } from "./use-auth"
const first = {
  username: "first@example.test",
  name: "First investigator",
  role: "user",
}
const second = {
  username: "second@example.test",
  name: "Second investigator",
  role: "user",
}
beforeEach(() => {
  queryClient.clear()
  localStorage.clear()
  useAuthStore.setState({ user: null, isAuthenticated: false })
})
it("does not offer the previous member's cached financial case after signing in as someone else", () => {
  useAuthStore.getState().login("first-token", first)
  queryClient.setQueryData(["financial-ledger", "private-case"], {
    rows: [{ description: "Private payment" }],
  })
  queryClient.setQueryData(["cases"], { cases: [{ id: "private-case" }] })
  useAuthStore.getState().login("second-token", second)
  expect(
    queryClient.getQueryData(["financial-ledger", "private-case"])
  ).toBeUndefined()
  expect(queryClient.getQueryData(["cases"])).toBeUndefined()
  expect(useAuthStore.getState().user?.username).toBe(second.username)
})
it("discards a late response from the previous session instead of returning it to the next member", async () => {
  useAuthStore.getState().login("first-token", first)
  let resolve!: (value: unknown) => void
  const request = queryClient
    .fetchQuery({
      queryKey: ["financial-ledger", "private-case"],
      queryFn: () =>
        new Promise((r) => {
          resolve = r
        }),
    })
    .catch(() => undefined)
  useAuthStore.getState().logout()
  useAuthStore.getState().login("second-token", second)
  resolve({ rows: [{ description: "Late private payment" }] })
  await request
  expect(
    queryClient.getQueryData(["financial-ledger", "private-case"])
  ).toBeUndefined()
})
it("clears case data on logout but retains the same member's active queries when refreshing their profile", () => {
  useAuthStore.getState().login("token", first)
  queryClient.setQueryData(["financial-ledger", "case"], { rows: [] })
  useAuthStore
    .getState()
    .setUser({ ...first, id: "member-id", name: "Updated name" })
  expect(queryClient.getQueryData(["financial-ledger", "case"])).toEqual({
    rows: [],
  })
  useAuthStore.getState().logout()
  expect(queryClient.getQueryData(["financial-ledger", "case"])).toBeUndefined()
  expect(localStorage.getItem("authToken")).toBeNull()
})
