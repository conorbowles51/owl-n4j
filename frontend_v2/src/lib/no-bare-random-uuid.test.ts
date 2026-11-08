import { expect, it } from "vitest"

// Loupe is served over plain http (an insecure context), where crypto.randomUUID does not exist and a direct
// call throws a TypeError on the press that makes it. App code uses randomRequestId from @/lib/browser-crypto,
// or an optional-chained call with a fallback.
const sources = import.meta.glob(["../**/*.ts", "../**/*.tsx", "!../**/*.test.ts", "!../**/*.test.tsx", "!../**/*.stories.tsx", "!./browser-crypto.ts"], {
  query: "?raw",
  import: "default",
  eager: true,
}) as Record<string, string>

it("never calls crypto.randomUUID directly in app code", () => {
  const found = Object.entries(sources).flatMap(([path, text]) =>
    text.split("\n").flatMap((line, n) =>
      /\bcrypto\.randomUUID\(/.test(line) && !line.trim().startsWith("//") ? [`${path}:${n + 1}: ${line.trim()}`] : []
    )
  )
  expect(Object.keys(sources).length).toBeGreaterThan(100)
  expect(found).toEqual([])
})
