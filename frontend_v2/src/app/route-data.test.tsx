import type { ReactNode } from "react"
import { QueryClientProvider } from "@tanstack/react-query"
import { act, render, renderHook, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { fetchAPI } from "@/lib/api-client"
import { queryClient } from "@/lib/query-client"
import { useAuthStore } from "@/features/auth/hooks/use-auth"
import { useCase, useCases } from "@/features/cases/hooks/use-cases"
import { useSnapshots } from "@/features/cases/hooks/use-snapshots"
import { useCaseProcessingProfile } from "@/features/evidence/hooks/use-case-processing-profile"
import { folderContentsParams, useFolderContents } from "@/features/evidence/hooks/use-folder-contents"
import { useFolderTree } from "@/features/evidence/hooks/use-folder-tree"
import { useEvidenceStore } from "@/features/evidence/evidence.store"
import { FinancialAccessProvider } from "@/features/financial/components/FinancialAccessProvider"
import { useFinancialCategories, useFinancialEntities } from "@/features/financial/hooks/use-financial-data"
import { useJudgementCounts } from "@/features/financial/hooks/use-judgements"
import { useLedgerAccountDirectory } from "@/features/financial/hooks/use-ledger-account-directory"
import { useLedgerOverview, useLedgerOverviewPanels } from "@/features/financial/hooks/use-ledger-overview"
import { useSignificantManifest } from "@/features/significant/hooks/use-significant"
import { preloadCurrentRoute } from "./route-table"

// The pages' code is not what this test is about: a stand-in that starts nothing.
vi.mock("@/lib/timed-lazy", () => ({
  timedLazy: () => Object.assign(() => null, { preload: () => {} }),
}))
vi.mock("@/lib/api-client", async (original) => ({
  ...(await original<typeof import("@/lib/api-client")>()),
  fetchAPI: vi.fn(),
}))

const C = "c1"
const USER = { id: "u1", username: "jobs", email: "jobs@x", role: "user", global_role: "user" }

/** A minimal valid answer per endpoint (each passes the page's own checks). */
function answer(url: string): unknown {
  const path = url.split("?")[0]
  if (path === `/api/significant/${C}`) return { case_id: C, entity_keys: [] }
  if (path === "/api/phones") return { case_id: C, phones: [], total: 0, case_zone: { name: "UTC", basis: "default", note: null } }
  if (path === "/api/financial/case-access") return { case_id: C, user_id: USER.id, can_edit: false, can_upload: false }
  if (path === "/api/financial/categories") return { categories: [] }
  if (path === "/api/financial/entities") return { entities: [] }
  if (path === "/api/financial/judgements/counts") return { case: {}, statements: {}, rules: [] }
  if (path === "/api/financial/ledger-overview") return { case_id: C }
  if (path === "/api/financial/ledger-overview-panel-figures")
    return { case_id: C, totals: { inventory: { accounts: [], banks: [], currencies: [] } }, connections: { groups: [] } }
  if (path === "/api/financial/ledger-accounts") return { case_id: C, has_more: false, items: [] }
  if (path === "/api/financial/statement-coverage")
    return { case_id: C, offset: 0, has_more: false, applied: false, limitation: "", items: [] }
  if (path === "/api/evidence-folders/tree") return { tree: [] }
  if (path === "/api/evidence-folders/root/contents") return { files: [], folders: [], total_files: 0 }
  if (path === `/api/cases/${C}/processing-profile`) return { case_id: C }
  if (path === `/api/cases/${C}`) return { id: C, title: "Case" }
  if (path === "/api/cases") return { cases: [], total: 0 }
  if (path === "/api/snapshots") return []
  throw new Error(`no answer for ${url}`)
}

const calls = () => vi.mocked(fetchAPI).mock.calls.map(([url]) => String(url))
const countsByUrl = () => calls().reduce<Record<string, number>>((n, u) => ({ ...n, [u]: (n[u] ?? 0) + 1 }), {})
const wrapper = ({ children }: { children: ReactNode }) => (
  <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
)
const settle = () => act(() => new Promise<void>((r) => setTimeout(r, 50)))

/** Opens the app at `path`: the start-up step, then the sign-in check answers. Returns the requests sent. */
async function openSignedIn(path: string, search = "") {
  window.history.replaceState(null, "", path + search)
  localStorage.setItem("authToken", "t")
  expect(preloadCurrentRoute(path, search)).toBe(true)
  await settle()
  // Requests that need the session wait for the sign-in check, exactly as the page's own do.
  expect(calls()).toEqual([])
  act(() => useAuthStore.setState({ user: USER as never, isAuthenticated: true }))
  await waitFor(() => expect(calls().length).toBeGreaterThan(0))
  // The case pages' phones request loads the phones API module first.
  if (path.startsWith("/cases/")) await waitFor(() => expect(calls().some((u) => u.startsWith("/api/phones?"))).toBe(true))
  await settle()
  return countsByUrl()
}

/** Every request was sent once by the start-up step, and the page's own hooks read it without asking again. */
async function pageReadsOnce(before: Record<string, number>, mount: () => void) {
  expect(Object.values(before).every((n) => n === 1)).toBe(true)
  mount()
  await settle()
  await settle()
  expect(countsByUrl()).toEqual(before)
}

beforeEach(() => {
  vi.mocked(fetchAPI).mockReset()
  vi.mocked(fetchAPI).mockImplementation(async (url: string) => answer(url) as never)
  queryClient.clear()
  useAuthStore.setState({ user: null, isAuthenticated: true })
})
afterEach(() => {
  queryClient.clear()
  localStorage.clear()
  sessionStorage.clear()
  useAuthStore.setState({ user: null, isAuthenticated: false })
  window.history.replaceState(null, "", "/")
})

describe("a fresh load starts the page's first data alongside its code", () => {
  it("Financial (Overview): sent at start-up once signed in, and the page asks for none of it again", async () => {
    const sent = await openSignedIn(`/cases/${C}/financial`)
    expect(Object.keys(sent).map((u) => u.split("?")[0]).sort()).toEqual([
      "/api/financial/case-access",
      "/api/financial/categories",
      "/api/financial/entities",
      "/api/financial/judgements/counts",
      "/api/financial/ledger-accounts",
      "/api/financial/ledger-overview",
      "/api/financial/ledger-overview-panel-figures",
      "/api/financial/statement-coverage",
      "/api/phones",
      `/api/significant/${C}`,
    ])
    await pageReadsOnce(sent, () => {
      renderHook(
        () => {
          useSignificantManifest(C)
          useLedgerOverview(C)
          useLedgerOverviewPanels(C)
          useFinancialCategories(C)
          useFinancialEntities(C)
          useJudgementCounts(C)
          useLedgerAccountDirectory(C)
        },
        { wrapper }
      )
      render(<FinancialAccessProvider caseId={C}>page</FinancialAccessProvider>, { wrapper })
    })
  })

  it("Financial opened on another view does not fetch the Overview's figures", async () => {
    const sent = await openSignedIn(`/cases/${C}/financial`, "?view=trends")
    expect(Object.keys(sent).some((u) => u.includes("ledger-overview"))).toBe(false)
    expect(Object.keys(sent).some((u) => u.includes("/api/financial/categories"))).toBe(true)
  })

  it("Evidence: the tree, the first page of files in the saved sort, the case, its profile and access", async () => {
    localStorage.setItem("evidence-preferences-v1", JSON.stringify({ sortBy: "date", sortDirection: "desc" }))
    useEvidenceStore.setState({ sortBy: "date", sortDirection: "desc" })
    const sent = await openSignedIn(`/cases/${C}/evidence`)
    expect(Object.keys(sent)).toContain(`/api/evidence-folders/root/contents?case_id=${C}&limit=250&sort_by=date&sort_direction=desc`)
    await pageReadsOnce(sent, () => {
      renderHook(
        () => {
          const list = useEvidenceStore.getState()
          useFolderTree(C)
          useFolderContents(C, null, folderContentsParams(list))
          useCaseProcessingProfile(C)
          useCase(C)
          useSignificantManifest(C)
        },
        { wrapper }
      )
      render(<FinancialAccessProvider caseId={C} quietFailure>page</FinancialAccessProvider>, { wrapper })
    })
  })

  it("the case list: its cases and snapshots", async () => {
    const sent = await openSignedIn("/cases")
    expect(Object.keys(sent).sort()).toEqual(["/api/cases", "/api/snapshots"])
    await pageReadsOnce(sent, () => {
      renderHook(() => {
        useCases(undefined, false)
        useSnapshots()
      }, { wrapper })
    })
  })

  it("signed out first: nothing is asked for", async () => {
    window.history.replaceState(null, "", `/cases/${C}/financial`)
    localStorage.setItem("authToken", "t")
    preloadCurrentRoute(`/cases/${C}/financial`)
    act(() => useAuthStore.setState({ user: null, isAuthenticated: false }))
    act(() => useAuthStore.setState({ user: USER as never, isAuthenticated: true }))
    await settle()
    expect(calls()).toEqual([])
  })

  it("left before the sign-in check answered: the old page's data is not asked for", async () => {
    window.history.replaceState(null, "", `/cases/${C}/financial`)
    localStorage.setItem("authToken", "t")
    preloadCurrentRoute(`/cases/${C}/financial`)
    await settle()
    window.history.replaceState(null, "", `/cases/${C}/graph`)
    act(() => useAuthStore.setState({ user: USER as never, isAuthenticated: true }))
    await settle()
    expect(calls()).toEqual([])
  })

  it("with the early sign-in check: the data starts when it answers, before the page has rendered", async () => {
    window.history.replaceState(null, "", `/cases/${C}/phones`)
    localStorage.setItem("authToken", "t")
    let answer!: (user: never) => void
    const signedIn = new Promise<never>((r) => { answer = r })
    expect(preloadCurrentRoute(`/cases/${C}/phones`, "", signedIn)).toBe(true)
    await settle()
    expect(calls()).toEqual([])
    act(() => answer(USER as never))
    await waitFor(() => expect(calls().some((u) => u.startsWith("/api/phones?"))).toBe(true))
    expect(useAuthStore.getState().user).toBeNull() // React has not set the user yet
  })
})

