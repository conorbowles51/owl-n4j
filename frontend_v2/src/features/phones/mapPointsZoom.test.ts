import { describe, expect, it, vi } from "vitest"

const fetchAPI = vi.hoisted(() => vi.fn())
vi.mock("@/lib/api-client", () => ({ fetchAPI }))

import { getPhoneMapPoints } from "./api"

describe("getPhoneMapPoints zoom", () => {
  it("sends a zoom the server accepts when the map is fitted to the whole world", async () => {
    fetchAPI.mockReset().mockResolvedValue({})
    await getPhoneMapPoints("c1", [-180, -40, 180, 70], -0.23).catch(() => undefined)
    expect(fetchAPI.mock.calls[0][1].body.zoom).toBe(0)
  })
})
