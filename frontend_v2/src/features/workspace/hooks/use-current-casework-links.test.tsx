import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { renderHook, waitFor } from "@testing-library/react"
import type { ReactNode } from "react"
import { afterEach, expect, it, vi } from "vitest"
import { graphAPI } from "@/features/graph/api"
import { useEvidenceStore } from "@/features/evidence/evidence.store"
import { useGraphStore } from "@/stores/graph.store"
import { caseworkAPI } from "../casework-api"
import { usePhoneSelection } from "@/stores/phone-selection.store"
import { useCurrentCaseworkLinks } from "./use-current-casework-links"

afterEach(() => {
  vi.restoreAllMocks()
  useGraphStore.setState({ selectedNodeKeys: new Set() })
  useEvidenceStore.setState({ selectedFileIds: new Set(), detailFileId: null })
  usePhoneSelection.setState({ caseId: null, ids: [], anchor: null, focus: null, whole: null })
})

it("returns the whole selection with a phone source and never cuts it to 6 (07 6.4 item 10)", async () => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const nodeKeys = Array.from({ length: 9 }, (_, n) => `node-${n}`)
  // Nodes already in the loaded graph are labelled from it; only the rest are fetched.
  client.setQueryData(["graph", "case-1", "all"], { nodes: nodeKeys.slice(0, 7).map((key) => ({ key, label: `Label ${key}`, type: "Person" })) })
  const details = vi.spyOn(graphAPI, "getNodeDetails").mockImplementation(
    (key: string) => Promise.resolve({ key, label: `Fetched ${key}` } as never))
  const fileIds = Array.from({ length: 60 }, (_, n) => `file-${n}`)
  const options = vi.spyOn(caseworkAPI, "attachmentOptions").mockImplementation(
    (_case, _type, _q, _limit, ids?: string[]) =>
      Promise.resolve({ items: (ids ?? []).map((id) => ({ target_type: "evidence", target_id: id, label: `Doc ${id}`, metadata: {} })) } as never))
  useGraphStore.setState({ selectedNodeKeys: new Set(nodeKeys) })
  useEvidenceStore.setState({ selectedFileIds: new Set(fileIds), detailFileId: null })
  usePhoneSelection.getState().setCase("case-1")
  usePhoneSelection.setState({ ids: Array.from({ length: 700 }, (_, n) => `rec-${n}`) })
  const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>
  const { result } = renderHook(() => useCurrentCaseworkLinks("case-1"), { wrapper })

  await waitFor(() => expect(result.current.filter((l) => l.target_label?.startsWith("Doc "))).toHaveLength(60))
  await waitFor(() => expect(result.current.filter((l) => l.target_label?.startsWith("Fetched "))).toHaveLength(2))
  expect(result.current).toHaveLength(9 + 60 + 700)
  expect(details.mock.calls.map((call) => call[0]).sort()).toEqual(["node-7", "node-8"])
  expect(options.mock.calls.map((call) => (call[4] ?? []).length)).toEqual([50, 10])
  const phone = result.current.filter((link) => link.target_type === "phone_record")
  expect(phone.map((link) => link.target_id)).toEqual(Array.from({ length: 700 }, (_, n) => `rec-${n}`))
  expect(phone[0].metadata).toMatchObject({ source: "current_selection" })
})

it("ignores a phone selection made in another case", () => {
  const client = new QueryClient()
  usePhoneSelection.getState().setCase("case-2")
  usePhoneSelection.setState({ ids: ["r1"] })
  const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>
  const { result } = renderHook(() => useCurrentCaseworkLinks("case-1"), { wrapper })
  expect(result.current).toEqual([])
})
