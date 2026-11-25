import { beforeEach, describe, expect, it, vi } from "vitest"
import { fireEvent, render, screen } from "@testing-library/react"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { Sheet, SheetContent, SheetTitle } from "@/components/ui/sheet"
import { setSwitch } from "@/lib/ui-switches"
import { CorroborateOpener } from "./CorroboratePanel"
import { CorroborateAction } from "./CorroborateAction"
import { readCorroborateRequest } from "./open"

// 23 Nov, live: a dossier sheet's Corroborate opened the panel behind the sheet, so the person saw nothing happen.
// Since lx-corroredo A nothing opens over the page: Corroborate in a sheet goes to the Corroborate page.
function page() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={qc}><MemoryRouter initialEntries={["/cases/c1/dossiers"]}>
    <CorroborateOpener />
    <Routes>
      <Route path="/cases/:id/dossiers" element={
        <Sheet open onOpenChange={() => undefined}>
          <SheetContent><SheetTitle>Mateo Ruiz</SheetTitle>
            <CorroborateAction caseId="c1" screen="Dossiers" label="Mateo Ruiz" members={[{ type: "person", id: "d1" }]} />
          </SheetContent>
        </Sheet>} />
      <Route path="/cases/:id/corroborate" element={<p>the Corroborate page</p>} />
    </Routes>
  </MemoryRouter></QueryClientProvider>)
}

beforeEach(() => { vi.restoreAllMocks(); sessionStorage.clear(); setSwitch("corroborate-v2", true) })

describe("Corroborate asked from an open sheet", () => {
  it("opens the Corroborate page with the sheet's person as the question's records", async () => {
    page()
    fireEvent.click(screen.getByRole("button", { name: "Corroborate" }))
    expect(await screen.findByText("the Corroborate page")).toBeTruthy()
    expect(screen.queryByRole("dialog", { name: "Corroborate" })).toBeNull()
    expect(readCorroborateRequest("c1")?.members).toEqual([{ type: "person", id: "d1" }])
  })
})
