import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { renderHook, waitFor } from "@testing-library/react"
import type { ReactNode } from "react"
import { afterEach, expect, it, vi } from "vitest"
import { graphAPI } from "@/features/graph/api"
import { useEvidenceStore } from "@/features/evidence/evidence.store"
import { useGraphStore } from "@/stores/graph.store"
import { caseworkAPI } from "../casework-api"
import { usePhoneSelectionStore } from "../stores/phone-selection.store"
import { useCurrentCaseworkLinks } from "./use-current-casework-links"

afterEach(() => {
  vi.restoreAllMocks()
  useGraphStore.setState({ selectedNodeKeys: new Set() })
  useEvidenceStore.setState({ selectedFileIds: new Set(), detailFileId: null })
  usePhoneSelectionStore.setState({ selection: null })
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
  usePhoneSelectionStore.setState({ selection: { caseId: "case-1", recordCount: 12345, screen: "Conversations", links: [
    { target_type: "phone_selection", target_id: "sel-1", target_label: "12,345 messages", relationship: "unclassified" },
  ] } })
  const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>
  const { result } = renderHook(() => useCurrentCaseworkLinks("case-1"), { wrapper })

  await waitFor(() => expect(result.current.filter((l) => l.target_label?.startsWith("Doc "))).toHaveLength(60))
  await waitFor(() => expect(result.current.filter((l) => l.target_label?.startsWith("Fetched "))).toHaveLength(2))
  expect(result.current).toHaveLength(9 + 60 + 1)
  expect(details.mock.calls.map((call) => call[0]).sort()).toEqual(["node-7", "node-8"])
  expect(options.mock.calls.map((call) => (call[4] ?? []).length)).toEqual([50, 10])
  const phone = result.current.at(-1)!
  expect(phone.target_type).toBe("phone_selection")
  expect(phone.metadata).toMatchObject({ source: "current_selection", screen: "Conversations" })
})

it("ignores a phone selection made in another case", () => {
  const client = new QueryClient()
  usePhoneSelectionStore.setState({ selection: { caseId: "case-2", recordCount: 1, screen: "Search", links: [
    { target_type: "phone_record", target_id: "r1" }] } })
  const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>
  const { result } = renderHook(() => useCurrentCaseworkLinks("case-1"), { wrapper })
  expect(result.current).toEqual([])
})
