import { beforeEach, describe, expect, it, vi } from "vitest"
import { act, fireEvent, render, screen } from "@testing-library/react"
import { MemoryRouter, useNavigate } from "react-router-dom"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { setSwitch } from "@/lib/ui-switches"
import { CorroboratePanel } from "./CorroboratePanel"
import { openCorroborate, takePendingCorroborate } from "./open"
import { leadsAPI } from "./api"
import { skippedWords, toMembers } from "@/features/relations/api"
import { LookIntoButton } from "@/features/relations/LookIntoButton"

// 23 Nov, live: the Corroborate panel was open on every phone screen, and Phone summary's Corroborate showed
// "Corroborate cannot read 1 phone_extraction". A request kept after a panel showed it reopened every panel mounted
// later (any other page); a whole phone was handed to Corroborate, which reads records, and its type name was printed.
function Go({ to }: { to: string }) {
  const nav = useNavigate()
  return <button onClick={() => nav(to)}>go {to}</button>
}
function page(panel = true) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={qc}><MemoryRouter initialEntries={["/cases/c1/phones"]}>
    {panel && <CorroboratePanel />}
    <Go to="/cases/c1/map" />
  </MemoryRouter></QueryClientProvider>)
}
const ask = () => openCorroborate({ caseId: "c1", screen: "Phones", label: "1 message", members: [{ type: "phone_record", id: "r1" } as never] }, { keep: false })

beforeEach(() => {
  vi.restoreAllMocks()
  takePendingCorroborate()
  setSwitch("corroborate-v2", true)
  vi.spyOn(leadsAPI, "here").mockResolvedValue({ leads: [], total: 0, finder: { status: "done" } })
})

describe("the Corroborate panel opens only when asked, on the page it was asked from", () => {
  it("a panel mounted after another one showed a request does not open by itself", async () => {
    const first = page()
    act(() => ask())
    await screen.findByRole("dialog", { name: "Corroborate" })
    first.unmount()
    page()
    expect(screen.queryByRole("dialog", { name: "Corroborate" })).toBeNull()
  })
  it("leaving the page closes it", async () => {
    page()
    act(() => ask())
    await screen.findByRole("dialog", { name: "Corroborate" })
    fireEvent.click(screen.getByRole("button", { name: "go /cases/c1/map" }))
    expect(screen.queryByRole("dialog", { name: "Corroborate" })).toBeNull()
  })
  it("a request made before the panel loaded is still shown once, on its own page", async () => {
    act(() => ask())
    page()
    await screen.findByRole("dialog", { name: "Corroborate" })
  })
})

describe("what Corroborate cannot read is said in plain words", () => {
  it("a whole phone is named as a phone, with what to choose instead, never by its type name", () => {
    const got = toMembers([{ target_type: "phone_extraction", target_id: "e1", target_label: "Phone 1" }])
    expect(got.members).toHaveLength(0)
    const words = skippedWords(got.skipped, true)
    expect(words).not.toMatch(/phone_extraction|_/)
    expect(words).toContain("a whole phone")
    expect(skippedWords([{ type: "something_new", count: 2 }])).not.toContain("something_new")
  })
  it("Corroborate on a whole phone is not offered as if it could run", () => {
    render(<MemoryRouter><LookIntoButton caseId="c1" surface="phone" items={[{ target_type: "phone_extraction", target_id: "e1", target_label: "Phone 1" }]} /></MemoryRouter>)
    expect(screen.getByRole("button", { name: /Corroborate/ })).toBeDisabled()
  })
})
