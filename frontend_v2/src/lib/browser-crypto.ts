import { sha256 } from "@noble/hashes/sha2.js"

// HTTP deployments expose getRandomValues, but not SubtleCrypto or randomUUID.
// Preserve the same byte checks in both contexts, without skipping validation.
export async function sha256Hex(
  input: Uint8Array | ArrayBuffer
): Promise<string> {
  const bytes = input instanceof Uint8Array ? input : new Uint8Array(input)
  let digest: Uint8Array
  if (globalThis.crypto?.subtle) {
    digest = new Uint8Array(
      await globalThis.crypto.subtle.digest("SHA-256", new Uint8Array(bytes))
    )
  } else {
    // Yield between chunks so large supporting files do not freeze the page.
    const hash = sha256.create()
    for (let offset = 0; offset < bytes.length; offset += 1024 * 1024) {
      hash.update(bytes.subarray(offset, offset + 1024 * 1024))
      if (offset + 1024 * 1024 < bytes.length)
        await new Promise<void>((resolve) => setTimeout(resolve, 0))
    }
    digest = hash.digest()
  }
  return Array.from(digest, (byte) => byte.toString(16).padStart(2, "0")).join(
    ""
  )
}

export function randomRequestId(): string {
  if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID()
  const bytes = new Uint8Array(16)
  globalThis.crypto.getRandomValues(bytes)
  bytes[6] = (bytes[6] & 0x0f) | 0x40
  bytes[8] = (bytes[8] & 0x3f) | 0x80
  const hex = Array.from(bytes, (byte) =>
    byte.toString(16).padStart(2, "0")
  ).join("")
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`
}
