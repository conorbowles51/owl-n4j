import { useState } from "react"
import { act, cleanup, render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { BrowserRouter, Link, useLocation } from "react-router-dom"
import { afterEach, describe, expect, it, vi } from "vitest"
import {
  initializeUnsavedHistoryGuard,
  useUnsavedHistoryGuard,
} from "./use-unsaved-history-guard"

const initialUrl = window.location.href
const initialState = window.history.state
initializeUnsavedHistoryGuard()

function Draft() {
  const [draft, setDraft] = useState("")
  useUnsavedHistoryGuard(!!draft, "Discard this test draft?")
  return (
    <label>
      Draft
      <input value={draft} onChange={(event) => setDraft(event.target.value)} />
    </label>
  )
}
function Journey() {
  const location = useLocation()
  const stage =
    new URLSearchParams(location.search).get("guard-stage") ?? "home"
  return (
    <>
      <h1>{stage}</h1>
      {stage === "edit" && <Draft />}
      <Link to="?guard-stage=edit">Edit</Link>
      <Link to="?guard-stage=next">Next</Link>
    </>
  )
}
function mount() {
  window.history.replaceState({ idx: 0 }, "", "?guard-stage=home")
  return render(
    <BrowserRouter>
      <Journey />
    </BrowserRouter>
  )
}

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
  window.history.replaceState(initialState, "", initialUrl)
})

describe("Unsaved draft history guard in Chromium", () => {
  for (const legacy of [false, true]) {
    it(`preserves drafts on cancelled Back, then allows confirmed Back${legacy ? " without Navigation API" : ""}`, async () => {
      if (legacy) vi.stubGlobal("navigation", undefined)
      const confirm = vi.spyOn(window, "confirm").mockReturnValue(false)
      const user = userEvent.setup()
      mount()
      await user.click(screen.getByRole("link", { name: "Edit" }))
      await user.type(
        screen.getByLabelText("Draft"),
        "Keep this investigation draft"
      )
      const index = window.history.state.idx
      act(() => window.history.back())
      await waitFor(() => expect(confirm).toHaveBeenCalledOnce(), {
        timeout: 2500,
      })
      await waitFor(() => expect(window.history.state.idx).toBe(index), {
        timeout: 2500,
      })
      expect(screen.getByLabelText("Draft")).toHaveValue(
        "Keep this investigation draft"
      )
      expect(window.location.search).toBe("?guard-stage=edit")
      confirm.mockReturnValue(true)
      act(() => window.history.back())
      await screen.findByRole("heading", { name: "home" }, { timeout: 2500 })
      expect(confirm).toHaveBeenCalledTimes(2)
      expect(screen.queryByLabelText("Draft")).toBeNull()
      act(() => window.history.forward())
      expect(
        await screen.findByLabelText("Draft", {}, { timeout: 2500 })
      ).toHaveValue("")
      expect(confirm).toHaveBeenCalledTimes(2)
    })
  }

  it("restores the original entry after a cancelled Forward without Navigation API", async () => {
    vi.stubGlobal("navigation", undefined)
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false)
    const user = userEvent.setup()
    mount()
    await user.click(screen.getByRole("link", { name: "Edit" }))
    await user.click(screen.getByRole("link", { name: "Next" }))
    act(() => window.history.back())
    await screen.findByLabelText("Draft", {}, { timeout: 2500 })
    await user.type(screen.getByLabelText("Draft"), "Still working")
    const index = window.history.state.idx
    act(() => window.history.forward())
    await waitFor(() => expect(confirm).toHaveBeenCalledOnce(), {
      timeout: 2500,
    })
    await waitFor(() => expect(window.history.state.idx).toBe(index), {
      timeout: 2500,
    })
    expect(screen.getByLabelText("Draft")).toHaveValue("Still working")
    expect(window.location.search).toBe("?guard-stage=edit")
    confirm.mockReturnValue(true)
    act(() => window.history.forward())
    await screen.findByRole("heading", { name: "next" }, { timeout: 2500 })
    expect(confirm).toHaveBeenCalledTimes(2)
  })

  it("requests unload confirmation only while a draft is dirty", async () => {
    const user = userEvent.setup()
    mount()
    await user.click(screen.getByRole("link", { name: "Edit" }))
    await user.type(screen.getByLabelText("Draft"), "Unsaved")
    const dirtyEvent = new Event("beforeunload", { cancelable: true })
    window.dispatchEvent(dirtyEvent)
    expect(dirtyEvent.defaultPrevented).toBe(true)
    await user.clear(screen.getByLabelText("Draft"))
    const cleanEvent = new Event("beforeunload", { cancelable: true })
    window.dispatchEvent(cleanEvent)
    expect(cleanEvent.defaultPrevented).toBe(false)
  })
})
