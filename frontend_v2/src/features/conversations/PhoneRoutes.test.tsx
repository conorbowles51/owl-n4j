import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen } from "@testing-library/react"
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom"
import { describe, expect, it, vi } from "vitest"
import { PhonesIndexPage } from "./PhoneRoutes"

const mocks = vi.hoisted(() => ({ phones: vi.fn(), media: vi.fn(), view: vi.fn() }))
vi.mock("@/features/phones/api", () => ({ getPhones: mocks.phones, getRecord: vi.fn(), getMediaDetail: mocks.media, getSavedView: mocks.view, failureText: (_e: unknown, w: string) => w }))
vi.mock("@/features/phones/components/ComparePhones", () => ({ ComparePhones: () => null }))

const phone = (id: string, label: string, standing: string) => ({
  extraction_id: id, label, standing, device: { manufacturer: null, model: null },
  counts: { messages: 1, calls: 0, locations: 0 },
})

function Where() {
  const l = useLocation()
  return <p data-testid="where">{l.pathname + l.search}</p>
}

function show(path: string) {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/cases/:id/phones" element={<PhonesIndexPage />} />
          <Route path="/cases/:id/phones/:extraction/records/media" element={<p>media page</p>} />
          <Route path="/cases/:id/conversations" element={<Where />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe("saved phone_file links (lx-collect)", () => {
  it("open the file on its phone's Media screen", async () => {
    mocks.phones.mockResolvedValue({ phones: [], total: 0 })
    mocks.media.mockResolvedValue({ file_uid: "f1", extraction_id: "x1" })
    show("/cases/case-1/phones?file=f1")
    expect(await screen.findByText("media page")).toBeInTheDocument()
    expect(mocks.media).toHaveBeenCalledWith("case-1", "f1")
  })
})

describe("saved phone_view links (07 section 6)", () => {
  it("open the screen the view was saved from, marked as the saved view so it states the count then and now", async () => {
    mocks.phones.mockResolvedValue({ phones: [], total: 0 })
    mocks.view.mockResolvedValue({ id: "v1", words: "w", location: "/cases/case-1/conversations?thread=t1", event_count_then: 3, event_count_now: 5, created_at: null, sentence: "", replaced: null })
    show("/cases/case-1/phones?view=v1")
    expect(await screen.findByTestId("where")).toHaveTextContent("/cases/case-1/conversations?thread=t1&saved_view=v1")
  })

  it("says so when the view is not in this case", async () => {
    mocks.phones.mockResolvedValue({ phones: [], total: 0 })
    mocks.view.mockRejectedValue(new Error("404"))
    show("/cases/case-1/phones?view=v2")
    expect(await screen.findByRole("alert")).toHaveTextContent("This saved view is not in this case.")
  })
})

describe("Phones list after a Replace (07 J-13b, 01 10.7)", () => {
  it("lists a retired report apart, so two reports of one phone never share a link name", async () => {
    mocks.phones.mockResolvedValue({ phones: [phone("n", "C1", "active"), phone("b", "C2", "active"), phone("o", "C1", "superseded")], total: 3 })
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <MemoryRouter initialEntries={["/cases/case-1/phones"]}>
          <Routes>
            <Route path="/cases/:id/phones" element={<PhonesIndexPage />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    )
    expect(await screen.findByRole("link", { name: /^C1$/ })).toHaveAttribute("href", "/cases/case-1/phones/n")
    const replaced = screen.getByRole("region", { name: "Replaced reports" })
    expect(replaced).toHaveTextContent("Replaced report: C1")
    expect(screen.getAllByRole("link", { name: /^C1\b/ })).toHaveLength(1) // the journeys open a phone by its name
    expect(screen.getByRole("link", { name: "Replaced report: C1" })).toHaveAttribute("href", "/cases/case-1/phones/o")
  })
})

describe("Phones in a case with no phone", () => {
  it("says what a phone report is, what can be added and how big, and opens Evidence with the phone choice", async () => {
    mocks.phones.mockResolvedValue({ phones: [], total: 0 })
    show("/cases/case-1/phones")
    const add = await screen.findByRole("region", { name: "Add a phone report" })
    expect(add).toHaveTextContent("A phone report is the export")
    expect(add).toHaveTextContent("Cellebrite report folder")
    expect(add).toHaveTextContent("ZIP file")
    expect(add).toHaveTextContent("8 GB")
    expect(screen.getByRole("link", { name: "Add a phone report" })).toHaveAttribute("href", "/cases/case-1/evidence?add=phone")
  })
})
