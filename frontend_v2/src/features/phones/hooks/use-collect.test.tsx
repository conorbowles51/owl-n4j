import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { renderHook, waitFor } from "@testing-library/react"
import type { ReactNode } from "react"
import { describe, expect, it, vi } from "vitest"

const net = vi.hoisted(() => ({ urls: [] as string[] }))
vi.mock("@/lib/api-client", async (orig) => ({
  ...(await orig<object>()),
  fetchAPI: vi.fn(async (url: string) => {
    net.urls.push(url)
    const ids = [...url.matchAll(/target_ids\[\]=([^&]+)/g)].map((m) => decodeURIComponent(m[1]))
    return { results: ids.map((id) => ({ target_id: id, summary: id === "r3" ? "In 1 dossier" : null })) }
  }),
}))
import { useUsedIn } from "./use-collect"

describe("useUsedIn (07 section 6.2)", () => {
  it("one load of a list whose rows arrive in 10 growths asks for the marks once, for every shown row", async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={qc}>{children}</QueryClientProvider>
    const { result, rerender } = renderHook(({ ids }) => useUsedIn("c", ids), { wrapper, initialProps: { ids: [] as string[] } })
    for (let n = 1; n <= 10; n++) {
      rerender({ ids: Array.from({ length: n }, (_, i) => `r${i}`) })
      await new Promise((r) => setTimeout(r, 20)) // windows land a few ms apart
    }
    await waitFor(() => expect(result.current.usedIn.r3).toBe("In 1 dossier"))
    await new Promise((r) => setTimeout(r, 300))
    const asked = net.urls.filter((u) => u.includes("/collections"))
    expect(asked).toHaveLength(1)
    expect([...asked[0].matchAll(/target_ids\[\]=/g)]).toHaveLength(10)
  })
})
