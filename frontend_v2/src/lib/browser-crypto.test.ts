import { createHash, webcrypto } from "node:crypto"
import { afterEach, expect, it, vi } from "vitest"
import { randomRequestId, sha256Hex } from "./browser-crypto"
afterEach(() => vi.unstubAllGlobals())
const nativeCrypto = globalThis.crypto
const httpCrypto = () =>
  vi.stubGlobal("crypto", {
    getRandomValues: nativeCrypto.getRandomValues.bind(nativeCrypto),
  })
it.each(["", "abc", "Amount €123.45\n", "a".repeat(1000000)])(
  "matches independent SHA-256 with and without native support for input %#",
  async (text) => {
    const bytes = new TextEncoder().encode(text)
    const expected = createHash("sha256").update(bytes).digest("hex")
    expect(await sha256Hex(bytes)).toBe(expected)
    httpCrypto()
    expect(await sha256Hex(bytes)).toBe(expected)
  }
)
it("hashes only the selected byte view and yields for multi-chunk input", async () => {
  httpCrypto()
  const bytes = new Uint8Array(2 * 1024 * 1024 + 129).fill(127)
  bytes[0] = 1
  bytes[bytes.length - 1] = 2
  const view = bytes.subarray(1, bytes.length - 1)
  let yielded = false
  setTimeout(() => {
    yielded = true
  }, 0)
  const expected = createHash("sha256").update(view).digest("hex")
  expect(await sha256Hex(view)).toBe(expected)
  expect(yielded).toBe(true)
  expect(await sha256Hex(new Uint8Array([1, 2, 3]).buffer)).toBe(
    createHash("sha256")
      .update(new Uint8Array([1, 2, 3]))
      .digest("hex")
  )
})
it("does not hide a native digest failure", async () => {
  vi.stubGlobal("crypto", {
    subtle: {
      digest: vi.fn().mockRejectedValue(Error("Native digest failed")),
    },
  })
  await expect(sha256Hex(new Uint8Array([1]))).rejects.toThrow(
    "Native digest failed"
  )
})
it("creates version 4 request IDs with secure random bytes on HTTP", () => {
  httpCrypto()
  const ids = new Set(Array.from({ length: 100 }, () => randomRequestId()))
  expect(ids.size).toBe(100)
  for (const id of ids)
    expect(id).toMatch(
      /^[a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$/
    )
  vi.stubGlobal("crypto", webcrypto)
  expect(randomRequestId()).toMatch(/^[a-f0-9-]{36}$/)
})
