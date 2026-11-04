import ts from "typescript"
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
  .filter((file) => /^import (?!type\b)[^;]*from ["']zod["']/m.test(sources[file]))
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

// What the import check above cannot see: a module-level line that derives a schema from a lazy one or reads it
// (`const B = A.extend(...)`, `A.shape.x`, `A.parse(...)` outside any function) builds it while the page's code loads
// without calling a z factory. Read from the source: any module-level use of a lazySchema name or of `z`, outside
// function bodies and type positions, is refused. Test fixtures (`__fixtures__`) are code for tests only.
const lazyNames = new Set(
  Object.values(sources).flatMap((text) => [...text.matchAll(/^(?:export )?const (\w+)(?:: [^=]+)? = lazySchema\(/gm)].map((m) => m[1])),
)

function moduleLevelUses(file: string, text: string): string[] {
  const sf = ts.createSourceFile(file, text, ts.ScriptTarget.Latest, true, file.endsWith("x") ? ts.ScriptKind.TSX : ts.ScriptKind.TS)
  const found: string[] = []
  // the lazy schemas this file can see: its own and those it imports (a name like `document` is lazy in one file
  // and the browser's global in another)
  const visible = new Set<string>([...text.matchAll(/^(?:export )?const (\w+)(?:: [^=]+)? = lazySchema\(/gm)].map((m) => m[1]))
  for (const st of sf.statements)
    if (ts.isImportDeclaration(st) && st.importClause?.namedBindings && ts.isNamedImports(st.importClause.namedBindings))
      for (const el of st.importClause.namedBindings.elements) if (lazyNames.has((el.propertyName ?? el.name).text)) visible.add(el.name.text)
  const visit = (node: ts.Node) => {
    if (ts.isFunctionLike(node) || ts.isClassLike(node) || ts.isTypeNode(node) || ts.isImportDeclaration(node)) return
    if ((ts.isPropertyAccessExpression(node) || ts.isElementAccessExpression(node)) && ts.isIdentifier(node.expression)) {
      const name = node.expression.text
      if (name === "z" || visible.has(name)) {
        found.push(`${file}:${sf.getLineAndCharacterOfPosition(node.getStart(sf)).line + 1} ${node.getText(sf).slice(0, 60)}`)
      }
    }
    ts.forEachChild(node, visit)
  }
  visit(sf)
  return found
}

describe("module-level code over lazy schemas", () => {
  it("knows the lazy schemas", () => {
    expect(lazyNames.size).toBeGreaterThan(200)
  })

  it("never reads, derives from or builds a schema outside a function", () => {
    const uses = Object.entries(sources)
      .filter(([file]) => !file.includes("/__fixtures__/") && file !== "/src/lib/lazy-schema.ts")
      .flatMap(([file, text]) => moduleLevelUses(file, text))
    expect(uses).toEqual([])
  })

  it("would refuse a derived schema at module level", () => {
    expect(moduleLevelUses("/x.ts", "const A = lazySchema(() => z.object({}))\nexport const B = A.extend({})")).toHaveLength(1)
    expect(moduleLevelUses("/x.ts", 'import { HitSchema } from "@/features/search/api"\nexport const B = HitSchema.array()')).toHaveLength(1)
    expect(moduleLevelUses("/x.ts", "export const C = z.string()")).toHaveLength(1)
    expect(moduleLevelUses("/x.ts", "export const D = lazySchema(() => z.string())\nexport type T = z.infer<typeof D>")).toEqual([])
  })
})
