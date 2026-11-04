import { act, renderHook, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import type { ReactNode } from "react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { useMediaBlur } from "./use-media-blur"

const api = vi.hoisted(() => ({ getSettings: vi.fn(), putOwnBlur: vi.fn() }))
vi.mock("../api", async (orig) => ({ ...(await orig<object>()), ...api }))

const settings = (default_on: boolean, own: boolean | null) => ({ case_id: "c", time_zone: null, effective: { name: "UTC", basis: "utc_default", note: null }, updated_at: null, updated_by: null, media_blur: { default_on, basis: "case_setting", words: "", set: default_on }, own_media_blur: own })
const wrapper = ({ children }: { children: ReactNode }) => (
  <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>{children}</QueryClientProvider>
)

describe("useMediaBlur (03 section 8.3, 07 4.11)", () => {
  beforeEach(() => {
    localStorage.clear()
    api.getSettings.mockReset()
    api.putOwnBlur.mockReset()
  })

  it("stays blurred while the setting loads and when it cannot be read", async () => {
    api.getSettings.mockRejectedValue(new Error("down"))
    const { result } = renderHook(() => useMediaBlur("c"), { wrapper })
    expect(result.current.on).toBe(true)
    await waitFor(() => expect(api.getSettings).toHaveBeenCalled())
    expect(result.current.on).toBe(true)
  })

  it("follows the case default until the person chooses", async () => {
    api.getSettings.mockResolvedValue(settings(false, null))
    const { result } = renderHook(() => useMediaBlur("c"), { wrapper })
    await waitFor(() => expect(result.current.on).toBe(false))
  })

  it("a choice on the person's account comes first, on any browser", async () => {
    localStorage.setItem("loupe.media.blur", "off")
    api.getSettings.mockResolvedValue(settings(false, true))
    const { result } = renderHook(() => useMediaBlur("c"), { wrapper })
    await waitFor(() => expect(result.current.caseDefault).toBeDefined())
    expect(result.current.on).toBe(true)
  })

  it("choosing saves to the account and keeps working if that fails", async () => {
    api.getSettings.mockResolvedValue(settings(true, null))
    api.putOwnBlur.mockRejectedValue(new Error("down"))
    const { result } = renderHook(() => useMediaBlur("c"), { wrapper })
    await waitFor(() => expect(result.current.caseDefault).toBeDefined())
    act(() => result.current.choose(false))
    await waitFor(() => expect(api.putOwnBlur).toHaveBeenCalledWith("c", false))
    await waitFor(() => expect(result.current.error).not.toBeNull())
    expect(result.current.on).toBe(false)
  })
})
