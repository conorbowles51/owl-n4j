import { beforeEach, expect, it } from "vitest"
import { useAccountPerspectiveStore } from "./account-perspective"
import type { AccountParties } from "../lib/account-parties"
beforeEach(() => useAccountPerspectiveStore.getState().reset())
it("keeps separate groups per case and removes duplicate selections", () => {
  const state = useAccountPerspectiveStore.getState()
  state.set("first", { accountIds: ["one", "one", "two"], partyCapture: null })
  state.set("second", { accountIds: ["three"], partyCapture: null })
  expect(useAccountPerspectiveStore.getState().cases.first.accountIds).toEqual([
    "one",
    "two",
  ])
  state.set("second", { accountIds: [], partyCapture: null })
  expect(useAccountPerspectiveStore.getState().cases.first.accountIds).toEqual([
    "one",
    "two",
  ])
})
it("refuses a party-link capture from another case", () => {
  expect(() =>
    useAccountPerspectiveStore.getState().set("first", {
      accountIds: ["one"],
      partyCapture: { case_id: "second" } as AccountParties,
    })
  ).toThrow("another case")
  expect(useAccountPerspectiveStore.getState().cases).toEqual({})
})
