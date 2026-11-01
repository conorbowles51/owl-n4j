import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import { MemoryRouter, Navigate, Route, Routes } from "react-router-dom"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { TooltipProvider } from "@/components/ui/tooltip"
import { AppSidebar } from "@/components/ui/sidebar"
import { dispatchKey, resetKeymapForTest } from "@/lib/keymap"
import { applySwitchesAtStart, isSwitchOn, setSwitch } from "@/lib/ui-switches"
import { TRAINING } from "../fixtures"
import PhonePrototypePage from "./PhonePrototypePage"
import { readingsFor } from "./NeedsDecisionProto"
import { topPeople } from "./proto-data"

vi.mock("@/stores/app.store", () => ({ useAppStore: () => ({ sidebarExpanded: true, toggleSidebar: vi.fn() }) }))
vi.mock("@/features/auth/hooks/use-auth", () => ({ useAuthStore: () => ({ user: { global_role: "user" } }) }))
vi.mock("@/features/significant/components/CaseLayerSwitcher", () => ({ CaseLayerSwitcher: () => <div>Layers</div> }))
vi.mock("@/hooks/use-media-query", () => ({ useMediaQuery: () => false }))

function app(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <TooltipProvider>
        <Routes>
          <Route path="/cases/:id" element={<p>Case home</p>} />
          <Route
            path="/cases/:id/phones-prototype/:view?"
            element={
              <div className="flex">
                <AppSidebar />
                <PhonePrototypePage />
              </div>
            }
          />
          <Route path="/cases/:id/*" element={<AppSidebar />} />
        </Routes>
      </TooltipProvider>
    </MemoryRouter>
  )
}

beforeEach(() => {
  localStorage.clear()
  resetKeymapForTest()
})
afterEach(() => resetKeymapForTest())

describe("the prototype switch (07 12.1 item D)", () => {
  it("is off: no sidebar entry, and the route goes back to the case", async () => {
    expect(isSwitchOn("phone-prototype")).toBe(false)
    app("/cases/case-1/workspace")
    expect(screen.queryByRole("link", { name: "Phones (prototype)" })).toBeNull()
  })
  it("off: the prototype address shows nothing of it", async () => {
    app("/cases/case-1/phones-prototype/summary")
    expect(await screen.findByText("Case home")).toBeInTheDocument()
    expect(screen.queryByText(/Prototype on synthetic phones/)).toBeNull()
  })
  it("?phone-prototype=on turns it on for this browser; =off turns it off", async () => {
    app("/cases/case-1/workspace?phone-prototype=on")
    expect(await screen.findByRole("link", { name: "Phones (prototype)" })).toHaveAttribute("href", "/cases/case-1/phones-prototype/summary")
    expect(isSwitchOn("phone-prototype")).toBe(true)
    act(() => setSwitch("phone-prototype", false))
    await waitFor(() => expect(screen.queryByRole("link", { name: "Phones (prototype)" })).toBeNull())
  })
})

describe("the switch survives the case redirect (live check 1 November)", () => {
  function redirecting(path: string) {
    return render(
      <MemoryRouter initialEntries={[path]}>
        <TooltipProvider>
          <Routes>
            <Route path="/cases/:id" element={<Navigate to="workspace" replace />} />
            <Route path="/cases/:id/*" element={<AppSidebar />} />
          </Routes>
        </TooltipProvider>
      </MemoryRouter>
    )
  }
  it("the redirect drops the query, so the sidebar alone never sees ?phone-prototype=on", async () => {
    redirecting("/cases/case-1?phone-prototype=on")
    await screen.findByRole("navigation")
    expect(screen.queryByRole("link", { name: "Phones (prototype)" })).toBeNull()
  })
  it("read at app start, before routing, the switch is on after the redirect", async () => {
    applySwitchesAtStart({ search: "?phone-prototype=on" })
    redirecting("/cases/case-1?phone-prototype=on")
    expect(await screen.findByRole("link", { name: "Phones (prototype)" })).toBeInTheDocument()
  })
})

describe("prototype screens on synthetic phones", () => {
  beforeEach(() => setSwitch("phone-prototype", true))

  it("Phone summary: verdict, Needs a decision, counts that equal their lists", async () => {
    app("/cases/case-1/phones-prototype/summary")
    expect(await screen.findByText(/Prototype on synthetic phones/)).toBeInTheDocument()
    expect(screen.getByTestId("verdict")).toHaveTextContent(/^Read in full: 582 records, .* to .*, \d apps\. \d things? needs? a decision\.$/)
    const top = topPeople(TRAINING, "C5")
    const link = screen.getByRole("link", { name: `${top[0].person.name} (${top[0].person.numbers[0]})` })
    expect(link.getAttribute("href")).toContain(`person=${top[0].key}`)
    const messagesWithPerson = TRAINING.messages.filter((m) => m.phone === "C5" && (m.from === top[0].key || m.to.includes(top[0].key))).length
    expect(top[0].messages).toBe(messagesWithPerson)
    expect(document.title).toBe("Phone summary (prototype) · Loupe")
  })

  it("phones-only shape: a phone with no owner number asks for the owner and no zone is stated", async () => {
    app("/cases/case-1/phones-prototype/summary?shape=phones-only")
    fireEvent.click(await screen.findByRole("button", { name: /C2/ }))
    expect(screen.getByText(/No owner number was found\. Person-level views stay off until an owner is set\./)).toBeInTheDocument()
    expect(screen.getByText(/This phone did not record its time zone\./)).toBeInTheDocument()
  })

  it("Conversations: a thread opens, j moves, r opens the docked panel, keys reach the list", async () => {
    app("/cases/case-1/phones-prototype/conversations?phone=C5")
    const rail = await screen.findByRole("navigation", { name: /^Threads/ })
    fireEvent.click(within(rail).getAllByRole("button")[0])
    expect(screen.getByTestId("result-count")).toHaveTextContent(/messages/)
    act(() => {
      dispatchKey(new KeyboardEvent("keydown", { key: "j", cancelable: true }))
      dispatchKey(new KeyboardEvent("keydown", { key: "r", cancelable: true }))
    })
    const panel = await screen.findByRole("complementary", { name: "Record" })
    expect(within(panel).getByText(/Mapped by the system, not yet confirmed/)).toBeInTheDocument()
    expect(screen.queryByRole("dialog")).toBeNull()
    act(() => {
      dispatchKey(new KeyboardEvent("keydown", { key: "j", cancelable: true }))
    })
    expect(screen.getByRole("complementary", { name: "Record" })).toBeInTheDocument()
  })

  it("Needs a decision: Looks right stays disabled until every kind of example is opened", async () => {
    app("/cases/case-1/phones-prototype/needs-a-decision")
    const r = readingsFor(TRAINING)[0]
    expect(await screen.findByRole("heading", { name: r.sentence })).toBeInTheDocument()
    const looks = screen.getByRole("button", { name: /Looks right/ })
    expect(looks).toBeDisabled()
    const details = document.querySelectorAll("details")
    expect(details.length).toBe(r.kinds.length)
    details.forEach((d) => {
      d.open = true
      fireEvent(d, new Event("toggle"))
    })
    await waitFor(() => expect(screen.getByRole("button", { name: /Looks right/ })).toBeEnabled())
    act(() => {
      dispatchKey(new KeyboardEvent("keydown", { key: "y", cancelable: true }))
    })
    await waitFor(() => expect(screen.getAllByRole("status").some((s) => /1 of \d+ checked/.test(s.textContent ?? ""))).toBe(true))
  })
})
