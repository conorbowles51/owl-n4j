import { afterEach, beforeEach, expect, it, vi } from "vitest"
import { fetchAPI } from "./api-client"
import { requestWords, requestsSince, resetRequestsForTest } from "./request-progress"

beforeEach(() => resetRequestsForTest())
afterEach(() => vi.unstubAllGlobals())

it("counts a large answer's bytes against the server's own length and returns the same value", async () => {
  const value = { rows: Array.from({ length: 4000 }, (_, id) => ({ id, description: "PAYMENT TO SUPPLIER" })) }
  const text = JSON.stringify(value)
  const bytes = new TextEncoder().encode(text)
  const seen: number[] = []
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      for (let offset = 0; offset < bytes.length; offset += 50000) controller.enqueue(bytes.slice(offset, offset + 50000))
      controller.close()
    },
  })
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(body, { headers: { "x-body-length": String(bytes.length) } })))
  const answer = fetchAPI<typeof value>("/api/financial/ledger?case_id=c")
  const result = await answer
  expect(result).toEqual(value)
  const [read] = requestsSince(0)
  seen.push(read.received)
  expect(read).toMatchObject({ what: "payments", total: bytes.length, received: bytes.length, failed: null })
  expect(read.ended).not.toBeNull()
  expect(read.answered).not.toBeNull()
})

it("reads characters split between chunks exactly as a whole answer would", async () => {
  // Names with accents, CJK and an emoji: 2-, 3- and 4-byte characters, cut at every byte offset by 7-byte chunks.
  const value = {
    rows: Array.from({ length: 3000 }, (_, id) => ({ id, to_name: `ARRENDO SERVICIOS AÑO ${id} 東京 💶 Müller` })),
  }
  const bytes = new TextEncoder().encode(JSON.stringify(value))
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      for (let offset = 0; offset < bytes.length; offset += 7) controller.enqueue(bytes.slice(offset, offset + 7))
      controller.close()
    },
  })
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(body, { headers: { "x-body-length": String(bytes.length) } })))
  const result = await fetchAPI<typeof value>("/api/financial/ledger?case_id=c")
  expect(JSON.stringify(result)).toBe(JSON.stringify(value))
  expect(requestsSince(0)[0]).toMatchObject({ received: bytes.length, failed: null })
})

it("records a failed read with the server's message, and writes not at all", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: "Server error" }), { status: 500 })))
  await expect(fetchAPI("/api/financial/ledger-accounts?case_id=c")).rejects.toMatchObject({ status: 500 })
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ ok: true }))))
  await fetchAPI("/api/financial/judgements", { method: "POST", body: {} })
  const reads = requestsSince(0)
  expect(reads).toHaveLength(1)
  expect(reads[0]).toMatchObject({ what: "accounts", failed: expect.stringMatching(/.+/) })
})

it("words paths by whole segments", () => {
  expect(requestWords("/api/financial/ledger?case_id=x")).toBe("payments")
  expect(requestWords("/api/financial/ledger-accounts?offset=200")).toBe("accounts")
  expect(requestWords("/api/financial/ledger/category-library")).toBe("the category list")
  expect(requestWords("/api/financial/ledger-first-view")).toBe("the payments overview")
  expect(requestWords("/api/financial/something-new")).toBe("something new")
})

it("unpacks a large answer in pieces after its bytes are in, counting rows, with the same value", async () => {
  const value = {
    transactions: Array.from({ length: 30000 }, (_, id) => ({ id, description: `PAYMENT "${id}" TO SUPPLIER \\ [x]`, amount: id / 3 })),
  }
  const bytes = new TextEncoder().encode(JSON.stringify(value))
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      for (let offset = 0; offset < bytes.length; offset += 65536) controller.enqueue(bytes.slice(offset, offset + 65536))
      controller.close()
    },
  })
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(body, { headers: { "x-body-length": String(bytes.length) } })))
  const result = await fetchAPI<typeof value>("/api/financial/ledger?case_id=c")
  expect(JSON.stringify(result)).toBe(JSON.stringify(value))
  expect(requestsSince(0)[0]).toMatchObject({ received: bytes.length, unpack: { done: 30000, total: 30000, unit: "rows" } })
})
