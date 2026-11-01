import { afterEach, beforeEach, expect, it, vi } from "vitest"
import { fetchAPI } from "./api-client"
import { requestWords, requestsSince, resetRequestsForTest, subscribeRequests } from "./request-progress"
import { unpackWords } from "@/features/financial/lib/load-progress"

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

it("reports 0 of N rows the moment rows start, then never backwards, to N of N, end to end through fetchAPI", async () => {
  const value = { transactions: Array.from({ length: 30000 }, (_, id) => ({ id, description: `PAYMENT ${id} [x] TO SUPPLIER WITH A LONGER RECORDED DESCRIPTION` })), total: 30000 }
  const bytes = new TextEncoder().encode(JSON.stringify(value))
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(bytes, { headers: { "x-body-length": String(bytes.length) } })))
  const seen: { done: number; total: number }[] = []
  const stop = subscribeRequests(() => {
    const unpack = requestsSince(0)[0]?.unpack
    if (unpack?.unit === "rows") seen.push({ done: unpack.done, total: unpack.total })
  })
  await fetchAPI("/api/financial/ledger?case_id=c")
  stop()
  expect(seen[0]).toEqual({ done: 0, total: 30000 })
  expect(unpackWords({ ...seen[0], unit: "rows" })).toBe("0 of 30,000 rows unpacked")
  expect(seen.at(-1)).toEqual({ done: 30000, total: 30000 })
  for (let index = 1; index < seen.length; index += 1) expect(seen[index].done).toBeGreaterThanOrEqual(seen[index - 1].done)
})

it("words the graph, timeline, case list and evidence folder reads", () => {
  expect(requestWords("/api/graph?case_id=c&lightweight=true")).toBe("the graph")
  expect(requestWords("/api/graph/node/abc?case_id=c")).toBe("node details")
  expect(requestWords("/api/timeline?case_id=c")).toBe("timeline events")
  expect(requestWords("/api/timeline/entries?case_id=c")).toBe("timeline additions")
  expect(requestWords("/api/cases")).toBe("cases")
  expect(requestWords("/api/evidence-folders/root/contents?case_id=c")).toBe("evidence folders")
  expect(requestWords("/api/evidence/abc")).toBe("evidence files")
})

it("gives the browser a turn while it decodes an answer whose bytes have all arrived", async () => {
  // d5b330d1 People, 1 Nov: 61 MB already buffered after a busy spell was decoded in one 1,001 ms step.
  const value = { rows: Array.from({ length: 4000 }, (_, id) => ({ id, description: "PAYMENT TO SUPPLIER" })) }
  const bytes = new TextEncoder().encode(JSON.stringify(value))
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      for (let offset = 0; offset < bytes.length; offset += 20000) controller.enqueue(bytes.slice(offset, offset + 20000))
      controller.close()
    },
  })
  let clock = 0
  vi.spyOn(performance, "now").mockImplementation(() => (clock += 10)) // every chunk "takes" 10 ms or more
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(body, { headers: { "x-body-length": String(bytes.length) } })))
  const answer = fetchAPI<typeof value>("/api/financial/ledger?case_id=c")
  // A task queued now runs at the browser's first turn: by then only part of the answer may have been decoded.
  let receivedAtFirstTurn = -1
  setTimeout(() => (receivedAtFirstTurn = requestsSince(0)[0]?.received ?? 0), 0)
  expect(await answer).toEqual(value)
  vi.restoreAllMocks()
  expect(receivedAtFirstTurn).toBeGreaterThanOrEqual(0)
  expect(receivedAtFirstTurn).toBeLessThan(bytes.length)
})
