import { act, render, renderHook, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import type { ReactNode } from "react"
import { useState } from "react"
import { MemoryRouter, useLocation } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"

const api = vi.hoisted(() => ({ scopePresets: vi.fn(), getPhones: vi.fn() }))
vi.mock("../people.api", async (orig) => ({ ...(await orig<typeof import("../people.api")>()), peopleAPI: { scopePresets: api.scopePresets } }))
vi.mock("@/features/phones/api", async (orig) => ({ ...(await orig<typeof import("@/features/phones/api")>()), getPhones: api.getPhones }))
import { ScopeBar, type Scope } from "./ScopeBar"
import { EMPTY_SCOPE, paramsToScopeIds, recallScope, rememberScope, scopeHref, scopeToParams, scopeWords } from "./scope"
import { useScopeMemory, useScopePresets, useUrlScope } from "./use-phone-scope"

/** 07 4.5: presets, the last 5 scopes, "Showing your last selection". Invented data only. */
const PHONE = (id: string, label: string, index: number) => ({ id, label, index })
const THREE: Scope = { ...EMPTY_SCOPE, phones: [PHONE("a", "C1", 0), PHONE("b", "C2", 1), PHONE("c", "C3", 2)] }

function wrap(start = "/cases/c1/map") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[start]}>{children}</MemoryRouter>
    </QueryClientProvider>
  )
}

beforeEach(() => {
  sessionStorage.clear()
  vi.clearAllMocks()
  api.getPhones.mockResolvedValue({ phones: [{ extraction_id: "a", label: "C1" }, { extraction_id: "b", label: "C2" }] })
  api.scopePresets.mockResolvedValue({ case_id: "c1", people: [
    { dossier_id: "d1", name: "Ana", identity_keys: ["phone:+1"], owned_phones: ["a"], appears_on: ["a", "b"] },
    { dossier_id: "d2", name: "Ben", identity_keys: ["phone:+2"], owned_phones: [], appears_on: ["b"] },
  ] })
})

describe("scope in the address", () => {
  it("carries a scope in the names Conversations reads and back", () => {
    const scope: Scope = { ...THREE, people: [{ key: "phone:+1", label: "Ana" }], mode: "sent-by", window: { from: "2023-03-01", to: "2023-03-31" }, kinds: ["call"] }
    const search = new URLSearchParams(scopeToParams(scope)).toString()
    const back = paramsToScopeIds(search)
    expect(back.people).toEqual(["phone:+1"])
    expect(back.mode).toBe("sent-by")
    expect(back.phones).toEqual(["a", "b", "c"])
    expect(back.window).toEqual({ from: "2023-03-01", to: "2023-03-31" })
    expect(back.kinds).toEqual(["call"])
    expect(scopeHref("/cases/c1/graph", scope, { scope: "phones" })).toContain("scope=phones")
  })

  it("an unknown mode reads as Involving, never as nothing", () => {
    expect(paramsToScopeIds("mode=sideways").mode).toBe("involving")
  })
})

describe("the last 5 scopes", () => {
  it("keeps five, newest first, and drops a repeat", () => {
    for (const d of ["1", "2", "3", "4", "5", "6"]) rememberScope("c1", { ...EMPTY_SCOPE, phones: [PHONE(d, `C${d}`, 0)] })
    rememberScope("c1", { ...EMPTY_SCOPE, phones: [PHONE("4", "C4", 0)] })
    const { recent, last } = recallScope("c1")
    expect(recent.map((s) => s.phones[0].id)).toEqual(["4", "6", "5", "3", "2"])
    expect(last?.phones[0].id).toBe("4")
  })

  it("does not take Everything for a selection, and each case keeps its own", () => {
    rememberScope("c1", EMPTY_SCOPE)
    expect(recallScope("c1").last).toBeNull()
    rememberScope("c2", THREE)
    expect(recallScope("c1").recent).toEqual([])
  })
})

describe("presets", () => {
  it("offers Phones of a person only when they own one, and Phones where they appear", async () => {
    const { result } = renderHook(() => useScopePresets("c1"), { wrapper: wrap() })
    await waitFor(() => expect(result.current.presets[1]?.scope.phones.map((p) => p.label)).toEqual(["C1", "C2"]))
    expect(result.current.presets.map((p) => p.label)).toEqual(["Phones of Ana", "Phones where Ana appears", "Phones where Ben appears"])
  })

  it("picks a preset from the bar", async () => {
    const pick = vi.fn()
    const user = userEvent.setup()
    render(<ScopeBar scope={EMPTY_SCOPE} onChange={pick} count={null} presets={[{ label: "Phones of Ana", scope: THREE }]} recent={[THREE]} />)
    await user.click(screen.getByRole("button", { name: "Presets" }))
    expect(await screen.findByText("Your last 1 scopes")).toBeInTheDocument()
    await user.click(screen.getByRole("menuitem", { name: "Phones of Ana" }))
    expect(pick).toHaveBeenCalledWith(THREE)
  })
})

function Memory({ canRestore = true }: { canRestore?: boolean }) {
  const [scope, setScope] = useState<Scope>(EMPTY_SCOPE)
  const memory = useScopeMemory("c1", scope, setScope, canRestore)
  return <ScopeBar scope={scope} onChange={setScope} count={null} recent={memory.recent} restored={memory.restored} />
}

describe("Showing your last selection", () => {
  it("brings back the session's last scope on a plain arrival, says so, and Reset clears it", async () => {
    rememberScope("c1", THREE)
    const user = userEvent.setup()
    render(<Memory />)
    expect(await screen.findByText(new RegExp(`Showing your last selection: ${scopeWords(THREE)}`))).toBeInTheDocument()
    await user.click(within(screen.getByText(/Showing your last selection/)).getByRole("button", { name: "Reset" }))
    expect(screen.queryByText(/Showing your last selection/)).not.toBeInTheDocument()
    expect(screen.getByText("Everything on every phone in this case")).toBeInTheDocument()
  })

  it("does not restore over a link that names something", () => {
    rememberScope("c1", THREE)
    render(<Memory canRestore={false} />)
    expect(screen.queryByText(/Showing your last selection/)).not.toBeInTheDocument()
    expect(screen.getByText("Everything on every phone in this case")).toBeInTheDocument()
  })
})

describe("a scope arriving by address", () => {
  it("shows the same chips and states what this screen cannot apply", async () => {
    const { result } = renderHook(() => useUrlScope("c1", { window: true }), { wrapper: wrap("/cases/c1/map?people=phone%3A%2B1&phones=a&from=2023-03-01&to=2023-03-31&kinds=call") })
    await waitFor(() => expect(result.current.scope.people[0].label).toBe("Ana"))
    await waitFor(() => expect(result.current.scope.phones[0].label).toBe("C1"))
    expect(result.current.notApplied).toEqual(["the people chosen", "the kinds of record"])
  })

  it("names a person with no dossier by their value", async () => {
    const { result } = renderHook(() => useUrlScope("c1", { people: true }), { wrapper: wrap("/cases/c1/map?people=phone%3A%2B9") })
    await waitFor(() => expect(api.scopePresets).toHaveBeenCalled())
    expect(result.current.scope.people[0].label).toBe("+9")
    expect(result.current.notApplied).toEqual([])
  })

  it("writes a change back to the address and keeps the screen's own parameters", async () => {
    const seen: string[] = []
    const { result } = renderHook(() => {
      seen.push(useLocation().search)
      return useUrlScope("c1", { window: true })
    }, { wrapper: wrap("/cases/c1/map?phone_point=1,2&phones=a") })
    act(() => result.current.apply({ ...EMPTY_SCOPE, phones: [PHONE("b", "C2", 1)] }))
    await waitFor(() => expect(seen.at(-1)).toBe("?phone_point=1%2C2&phones=b"))
  })
})
