import { beforeEach, expect, it } from "vitest"
import { useStatementWorkspace as store } from "./statement-workspace"
const key = "loupe-statement-workspace"
const empty = {
  selections: {},
  pages: {},
  reviewChoices: {},
  sectionSearches: {},
}
beforeEach(() => {
  sessionStorage.clear()
  store.setState(empty)
})
it("restores the same file, period, currency, page and search after refresh, separated by user/case", async () => {
  const first = "member-a:case-one",
    second = "member-b:case-one",
    otherCase = "member-a:case-two"
  store.getState().select(first, "file-a")
  store
    .getState()
    .setReviewChoice(`${first}:file-a`, {
      statementId: "period-a",
      currency: "USD",
    })
  store.getState().setPage(`${first}:file-a:revision-a`, 15)
  store.getState().setSectionSearch(`${first}:file-a`, "2020-09")
  store.getState().select(second, "file-b")
  store.getState().select(otherCase, "file-c")
  const saved = sessionStorage.getItem(key)!
  store.setState(empty)
  sessionStorage.setItem(key, saved)
  await store.persist.rehydrate()
  expect(store.getState().selections[first]).toEqual({
    fileId: "file-a",
    open: true,
  })
  expect(store.getState().selections[second].fileId).toBe("file-b")
  expect(store.getState().selections[otherCase].fileId).toBe("file-c")
  expect(store.getState().reviewChoices[`${first}:file-a`]).toEqual({
    statementId: "period-a",
    currency: "USD",
  })
  expect(store.getState().pages[`${first}:file-a:revision-a`]).toBe(15)
  expect(store.getState().pages[`${first}:file-a:revision-b`]).toBeUndefined()
  expect(store.getState().sectionSearches[`${first}:file-a`]).toBe("2020-09")
  expect(store.getState().sectionSearches[`${second}:file-a`]).toBeUndefined()
  expect(Object.keys(JSON.parse(saved).state).sort()).toEqual(
    Object.keys(empty).sort()
  )
})
it("remembers an explicit close without forgetting which file to reopen", async () => {
  store.getState().select("member:case", "file")
  store.getState().setOpen("member:case", false)
  const saved = sessionStorage.getItem(key)!
  store.setState(empty)
  sessionStorage.setItem(key, saved)
  await store.persist.rehydrate()
  expect(store.getState().selections["member:case"]).toEqual({
    fileId: "file",
    open: false,
  })
})
it("rejects malformed saved locations and keeps store actions available", async () => {
  sessionStorage.setItem(
    key,
    JSON.stringify({
      version: 1,
      state: {
        selections: { scope: { fileId: "file", open: "yes" } },
        pages: { scope: -2 },
        select: "not a function",
      },
    })
  )
  await store.persist.rehydrate()
  expect(store.getState().selections).toEqual({})
  store.getState().select("member:case", "safe-file")
  expect(store.getState().selections["member:case"].fileId).toBe("safe-file")
})
