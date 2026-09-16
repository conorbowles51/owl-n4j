import {
  useFinancialDraftStore,
  financialDraftKey,
} from "../stores/financial-drafts"
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { beforeEach, expect, it } from "vitest"
import {
  Link,
  MemoryRouter,
  Route,
  Routes,
  useLocation,
  useNavigate,
  useParams,
} from "react-router-dom"
import { useFinancialViewNavigation } from "./use-financial-view-navigation"
import { useFinancialStore } from "../stores/financial.store"

function Financial() {
  const { id } = useParams()
  useFinancialViewNavigation(id)
  const view = useFinancialStore((state) => state.mainView)
  return (
    <>
      <output aria-label="Financial tab">{view}</output>
      <Link to={`/cases/${id}/workspace`}>Workspace</Link>
    </>
  )
}
function Location() {
  const location = useLocation(),
    navigate = useNavigate()
  return (
    <>
      <output aria-label="Location">
        {location.pathname}
        {location.search}
      </output>
      <button onClick={() => navigate(-1)}>Back</button>
      <Link to="/cases/second/financial">Another case</Link>
    </>
  )
}
function setup(path = "/cases/first/financial") {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Location />
      <Routes>
        <Route path="/cases/:id/financial" element={<Financial />} />
        <Route path="/cases/:id/workspace" element={<h1>Saved casework</h1>} />
      </Routes>
    </MemoryRouter>
  )
}
beforeEach(() => {
  useFinancialStore.getState().reset()
  useFinancialDraftStore.setState({ drafts: {} })
})
it("retains a requested tab across an outside route and browser Back", async () => {
  setup("/cases/first/financial?view=findings")
  expect(screen.getByLabelText("Financial tab")).toHaveTextContent("findings")
  fireEvent.click(screen.getByRole("link", { name: "Workspace" }))
  await screen.findByRole("heading", { name: "Saved casework" })
  act(() => useFinancialStore.getState().setMainView("transactions"))
  expect(screen.getByLabelText("Location")).toHaveTextContent(
    "/cases/first/workspace"
  )
  fireEvent.click(screen.getByRole("button", { name: "Back" }))
  await waitFor(() =>
    expect(screen.getByLabelText("Financial tab")).toHaveTextContent("findings")
  )
  expect(screen.getByLabelText("Location")).toHaveTextContent("?view=findings")
})
it("writes tab changes from any financial control while preserving unrelated query parameters", async () => {
  const mounted = setup("/cases/first/financial?source=sample")
  act(() => useFinancialStore.getState().setMainView("statements"))
  await waitFor(() =>
    expect(screen.getByLabelText("Location")).toHaveTextContent(
      "source=sample&view=statements"
    )
  )
  act(() => useFinancialStore.getState().setMainView("posting-graph"))
  await waitFor(() =>
    expect(screen.getByLabelText("Location")).toHaveTextContent(
      "source=sample&view=posting-graph"
    )
  )
  const url = screen.getByLabelText("Location").textContent!
  mounted.unmount()
  useFinancialStore.getState().reset()
  setup(url)
  expect(screen.getByLabelText("Financial tab")).toHaveTextContent(
    "posting-graph"
  )
})
it("opens a different unqualified case on Overview instead of retaining the first case's tab", async () => {
  setup("/cases/first/financial?view=tracing")
  fireEvent.click(screen.getByRole("link", { name: "Another case" }))
  await waitFor(() =>
    expect(screen.getByLabelText("Financial tab")).toHaveTextContent("overview")
  )
  expect(screen.getByLabelText("Location").textContent).toBe(
    "/cases/second/financial"
  )
})
it("falls back to Overview for an unsupported tab", () => {
  setup("/cases/first/financial?view=unknown")
  expect(screen.getByLabelText("Financial tab")).toHaveTextContent("overview")
})
it("retains Other financial records in the URL across refresh and tab changes", async () => {
  const first = setup()
  act(() => useFinancialStore.getState().setMode("intelligence"))
  await waitFor(() =>
    expect(screen.getByLabelText("Location")).toHaveTextContent(
      "dataset=other-records"
    )
  )
  act(() => useFinancialStore.getState().setMainView("trends"))
  await waitFor(() =>
    expect(screen.getByLabelText("Location")).toHaveTextContent(
      "view=trends&dataset=other-records"
    )
  )
  act(() => useFinancialStore.getState().setCurrentPage(3))
  act(() => useFinancialStore.getState().setMainView("counterparties"))
  expect(useFinancialStore.getState().currentPage).toBe(3)
  const url = screen.getByLabelText("Location").textContent!
  first.unmount()
  useFinancialStore.getState().reset()
  setup(url)
  expect(useFinancialStore.getState().mode).toBe("intelligence")
  expect(screen.getByLabelText("Financial tab")).toHaveTextContent(
    "counterparties"
  )
  act(() => useFinancialStore.getState().setMode("transactions"))
  await waitFor(() =>
    expect(screen.getByLabelText("Location")).not.toHaveTextContent("dataset=")
  )
})
it("does not carry the other-records dataset to a fresh case URL", async () => {
  setup("/cases/first/financial?dataset=other-records")
  expect(useFinancialStore.getState().mode).toBe("intelligence")
  fireEvent.click(screen.getByRole("link", { name: "Another case" }))
  await waitFor(() =>
    expect(useFinancialStore.getState().mode).toBe("transactions")
  )
})

it("restores the last page for this case without leaking another case's page", () => {
  useFinancialDraftStore
    .getState()
    .put(financialDraftKey("first", "last-view"), "counterparties")
  useFinancialDraftStore
    .getState()
    .put(financialDraftKey("second", "last-view"), "trends")
  setup("/cases/first/financial")
  expect(screen.getByLabelText("Financial tab")).toHaveTextContent(
    "counterparties"
  )
})
it("honours an explicit page over the remembered page", () => {
  useFinancialDraftStore
    .getState()
    .put(financialDraftKey("first", "last-view"), "counterparties")
  setup("/cases/first/financial?view=statements")
  expect(screen.getByLabelText("Financial tab")).toHaveTextContent("statements")
})
