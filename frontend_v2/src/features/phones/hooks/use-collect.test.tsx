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
  const setup = () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={qc}>{children}</QueryClientProvider>
    net.urls = []
    return renderHook(({ ids, complete }) => useUsedIn("c", ids, complete), { wrapper, initialProps: { ids: [] as string[], complete: false } })
  }
  const asked = () => net.urls.filter((u) => u.includes("/collections"))

  it("one load of a list whose rows arrive in 10 windows asks for the marks once, when the rows are all there", async () => {
    const { result, rerender } = setup()
    for (let n = 1; n <= 10; n++) {
      rerender({ ids: Array.from({ length: n }, (_, i) => `r${i}`), complete: n === 10 })
      await new Promise((r) => setTimeout(r, 400)) // live windows land a few hundred ms apart
    }
    await waitFor(() => expect(result.current.usedIn.r3).toBe("In 1 dossier"))
    expect(asked()).toHaveLength(1)
    expect([...asked()[0].matchAll(/target_ids\[\]=/g)]).toHaveLength(10)
  })

  it("rows still loading that stop changing are asked for after a wait, so a window that never arrives holds back nothing", async () => {
    const { result, rerender } = setup()
    rerender({ ids: ["r1", "r3"], complete: false })
    await new Promise((r) => setTimeout(r, 300))
    expect(asked()).toHaveLength(0)
    await waitFor(() => expect(result.current.usedIn.r3).toBe("In 1 dossier"), { timeout: 3000 })
    expect(asked()).toHaveLength(1)
  })
})
