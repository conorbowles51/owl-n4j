import "@testing-library/jest-dom/vitest"
import { configure } from "@testing-library/react"

// In jsdom, the first role query after a React update recomputes styles for
// every element against jsdom's default stylesheet. On the financial screens
// one query measured 1.2-1.8 s with no other load, and about three times that
// on a busy box. The 1 s default cannot fit even one check, so findBy and
// waitFor failed on load alone. With the job fleet running (load average
// 24-40, 2026-10-29) one check on the review queue's 50-item page took over
// 10 s, failing a passing journey. On 5 Nov two checks that take 14-30 s at load
// ~35 ran out of 30 s in the head suite (41 s in all) and passed alone. Nothing
// here asserts speed: this only says how long a check waits before it gives up.
configure({ asyncUtilTimeout: 60_000 })

if (typeof Element.prototype.scrollIntoView !== "function") {
  Element.prototype.scrollIntoView = () => undefined
}

if (typeof globalThis.localStorage?.getItem !== "function") {
  const values = new Map<string, string>()
  const storage: Storage = {
    get length() {
      return values.size
    },
    clear: () => values.clear(),
    getItem: (key) => values.get(key) ?? null,
    key: (index) => Array.from(values.keys())[index] ?? null,
    removeItem: (key) => values.delete(key),
    setItem: (key, value) => values.set(key, String(value)),
  }

  Object.defineProperty(globalThis, "localStorage", {
    configurable: true,
    value: storage,
  })
}
