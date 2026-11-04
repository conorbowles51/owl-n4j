import { describe, expect, it, vi } from "vitest"

// Importing a module must build no zod schema of its own accord: every module-level schema is declared with
// lazySchema(() => ...) so its construction happens on first use, not while the page's code loads (zod v4
// construction cost ~1.9 s of main-thread time per Financial page load when schemas were built at import). A schema
// used while a module loads (a saved store parsing its saved state) is built then, inside its lazySchema: allowed.
const zodCalls = vi.hoisted(() => ({ armed: false, calls: [] as string[], inLazyBuild: 0 }))

vi.mock("@/lib/lazy-schema", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/lazy-schema")>()
  return {
    lazySchema: <T extends object>(build: () => T) =>
      actual.lazySchema(() => {
        zodCalls.inLazyBuild += 1
        try {
          return build()
        } finally {
          zodCalls.inLazyBuild -= 1
        }
      }),
  }
})

vi.mock("zod", async (importOriginal) => {
  const actual = await importOriginal<typeof import("zod")>()
  const counted = new Proxy(actual.z, {
    get(target, key, receiver) {
      const value = Reflect.get(target, key, receiver)
      // Lower-case members are the schema factories (z.object, z.string, ...); capitalised ones are classes used
      // with instanceof and are passed through untouched.
      if (typeof value !== "function" || typeof key !== "string" || !/^[a-z]/.test(key)) return value
      return (...args: unknown[]) => {
        if (zodCalls.armed && !zodCalls.inLazyBuild) zodCalls.calls.push(key)
        return (value as (...a: unknown[]) => unknown)(...args)
      }
    },
  })
  return { ...actual, z: counted, default: counted }
})

const sources = import.meta.glob<string>(["/src/**/*.{ts,tsx}", "!/src/**/*.test.{ts,tsx}", "!/src/**/*.stories.tsx", "!/src/test/**"], {
  query: "?raw",
  import: "default",
  eager: true,
})
const modules = import.meta.glob(["/src/**/*.{ts,tsx}", "!/src/**/*.test.{ts,tsx}", "!/src/**/*.stories.tsx", "!/src/test/**"])
const zodModules = Object.keys(sources)
  .filter((file) => /^import \{[^}]*\bz\b[^}]*\} from ["']zod["']/m.test(sources[file]))
  .sort()

describe("module-level zod schemas", () => {
  it("finds the modules that declare schemas", () => {
    expect(zodModules.length).toBeGreaterThan(100)
  })

  // One case per module, so each import has its own time budget on a loaded machine. A module imported earlier as a
  // dependency of another resolves at once here; its schemas were counted against the module that pulled it in.
  it.each(zodModules)("%s builds no schema when imported", async (file) => {
    zodCalls.calls = []
    zodCalls.armed = true
    try {
      await modules[file]()
    } finally {
      zodCalls.armed = false
    }
    expect([...new Set(zodCalls.calls)]).toEqual([])
  })
})
