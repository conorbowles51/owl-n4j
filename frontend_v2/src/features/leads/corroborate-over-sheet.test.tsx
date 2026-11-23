import { beforeEach, describe, expect, it, vi } from "vitest"
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { Sheet, SheetContent, SheetTitle } from "@/components/ui/sheet"
import { setSwitch } from "@/lib/ui-switches"
import { CorroboratePanel } from "./CorroboratePanel"
import { CorroborateAction } from "./CorroborateAction"
import { leadsAPI } from "./api"
import { otherDialogOpen } from "@/features/guidance/other-dialog"

// 23 Nov, live: a dossier sheet's Corroborate opened the panel behind the sheet (both z-50, the sheet later in the page),
// and an open sheet keeps clicks and focus inside itself, so the person saw nothing happen.
function page() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={qc}><MemoryRouter>
    <CorroboratePanel />
    <Sheet open onOpenChange={() => undefined}>
      <SheetContent><SheetTitle>Mateo Ruiz</SheetTitle>
        <CorroborateAction caseId="c1" screen="Dossiers" label="Mateo Ruiz" members={[{ type: "dossier", id: "d1" } as never]} />
      </SheetContent>
    </Sheet>
  </MemoryRouter></QueryClientProvider>)
}

beforeEach(() => {
  vi.restoreAllMocks()
  setSwitch("corroborate-v2", true)
  vi.spyOn(leadsAPI, "here").mockResolvedValue({ leads: [], total: 0, finder: { status: "done" } })
})

describe("Corroborate asked from an open sheet", () => {
  it("draws the panel inside the sheet, on top, and the panel's tour is not pushed aside by the sheet", async () => {
    page()
    expect(otherDialogOpen()).toBe(true) // the sheet alone covers the page's tours
    fireEvent.click(screen.getByRole("button", { name: "Corroborate" }))
    const panel = await screen.findByRole("dialog", { name: "Corroborate" })
    const sheet = document.querySelector("[data-slot='sheet-content']")!
    await waitFor(() => expect(sheet.contains(panel)).toBe(true))
    expect(otherDialogOpen()).toBe(false)
  })

  it("Escape closes the panel and leaves the sheet open", async () => {
    page()
    fireEvent.click(screen.getByRole("button", { name: "Corroborate" }))
    await screen.findByRole("dialog", { name: "Corroborate" })
    await act(async () => { fireEvent.keyDown(document.activeElement ?? document.body, { key: "Escape" }) })
    expect(screen.queryByRole("dialog", { name: "Corroborate" })).toBeNull()
    expect(document.querySelector("[data-slot='sheet-content'][data-state='open']")).toBeTruthy()
  })
})
