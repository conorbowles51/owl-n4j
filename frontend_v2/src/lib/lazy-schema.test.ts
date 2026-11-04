import { describe, expect, it, vi } from "vitest"
import { z } from "zod"

import { lazySchema } from "./lazy-schema"

describe("lazySchema", () => {
  it("builds the schema on first use, once, and not before", () => {
    const build = vi.fn(() => z.object({ id: z.string(), amount: z.number().optional() }))
    const schema = lazySchema(build)
    expect(build).not.toHaveBeenCalled()

    expect(schema.parse({ id: "a", amount: 2, extra: 1 })).toEqual({ id: "a", amount: 2 })
    expect(schema.safeParse({ id: 1 }).success).toBe(false)
    expect(build).toHaveBeenCalledTimes(1)
  })

  it("parses, fails and transforms exactly as the schema it wraps", () => {
    const make = () =>
      z.object({
        id: z.string(),
        when: z.string().transform((value) => value.slice(0, 4)),
        kind: z.enum(["in", "out"]).default("in"),
      })
    const eager = make()
    const lazy = lazySchema(make)
    const inputs: unknown[] = [
      { id: "x", when: "2026-11-04" },
      { id: "x", when: "2026-11-04", kind: "out" },
      { id: 3, when: "2026" },
      { id: "x", when: "2026", kind: "sideways" },
      null,
    ]
    for (const input of inputs) {
      const a = eager.safeParse(input)
      const b = lazy.safeParse(input)
      expect(b.success).toBe(a.success)
      if (a.success && b.success) expect(b.data).toEqual(a.data)
      else expect(b.error?.issues).toEqual(a.error?.issues)
    }
    expect(() => lazy.parse({ id: 3 })).toThrow(z.ZodError)
  })

  it("is a zod schema to zod and to callers: instanceof, shape, extend, nesting, optional", () => {
    const Inner = lazySchema(() => z.object({ name: z.string() }))
    const Outer = lazySchema(() => z.object({ inner: Inner, list: z.array(Inner) }))
    const Extended = lazySchema(() => Inner.extend({ age: z.number() }))

    expect(Inner).toBeInstanceOf(z.ZodObject)
    expect(Inner instanceof z.ZodType).toBe(true)
    expect(Object.keys(Inner.shape)).toEqual(["name"])
    expect(Outer.parse({ inner: { name: "a" }, list: [{ name: "b" }] })).toEqual({
      inner: { name: "a" },
      list: [{ name: "b" }],
    })
    expect(Outer.safeParse({ inner: { name: 1 }, list: [] }).success).toBe(false)
    expect(Extended.parse({ name: "a", age: 3 })).toEqual({ name: "a", age: 3 })
    expect(Inner.optional().parse(undefined)).toBeUndefined()
    expect(z.union([Inner, z.null()]).parse(null)).toBeNull()
    expect(z.discriminatedUnion("t", [
      lazySchema(() => z.object({ t: z.literal("a"), a: z.string() })),
      lazySchema(() => z.object({ t: z.literal("b"), b: z.number() })),
    ]).parse({ t: "b", b: 1 })).toEqual({ t: "b", b: 1 })
  })

  it("keeps recursive schemas working", () => {
    type Node = { name: string; children: Node[] }
    const Tree: z.ZodType<Node> = lazySchema(() =>
      z.object({ name: z.string(), children: z.lazy(() => z.array(Tree)) }),
    )
    expect(Tree.parse({ name: "r", children: [{ name: "c", children: [] }] })).toEqual({
      name: "r",
      children: [{ name: "c", children: [] }],
    })
  })
})
