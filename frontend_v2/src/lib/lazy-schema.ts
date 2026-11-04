// A module-level schema built on first use instead of when its module loads.
//
// zod v4 gives every schema its own copies of ~60 methods when it is constructed, so a module that declares a few
// dozen schemas spends tens of milliseconds of main-thread time before the page can paint, whether or not the page
// ever parses with them. `lazySchema(() => z.object(...))` returns a stand-in that builds the schema the first time
// anything reads from it (`.parse`, `.shape`, `.extend`, use inside another schema, ...) and from then on forwards
// every read to that one built schema, so behaviour is the schema's own.
//
// Two limits. The stand-in cannot be frozen or sealed: Object.freeze / Object.preventExtensions on it throw at once
// and leave it working (a non-extensible stand-in would break every later Object.keys with a proxy invariant
// error). And the stand-in is a different object from the built schema, so anything keyed on schema identity (a zod
// registry, .meta(), z.toJSONSchema) sees two objects; nothing in the app uses those today. Use the stand-in for
// parsing and composing, and build the schema directly where identity matters.
export function lazySchema<T extends object>(build: () => T): T {
  let built: T | undefined
  const schema = (): T => (built ??= build())
  return new Proxy({} as T, {
    get: (_target, key) => Reflect.get(schema(), key),
    set: (_target, key, value) => Reflect.set(schema(), key, value),
    has: (_target, key) => Reflect.has(schema(), key),
    deleteProperty: (_target, key) => Reflect.deleteProperty(schema(), key),
    ownKeys: () => Reflect.ownKeys(schema()),
    getOwnPropertyDescriptor: (_target, key) => {
      const descriptor = Reflect.getOwnPropertyDescriptor(schema(), key)
      // The stand-in's own target is an empty, extensible object: a proxy may only report a property it lacks as
      // configurable.
      return descriptor && { ...descriptor, configurable: true }
    },
    defineProperty: (_target, key, descriptor) => Reflect.defineProperty(schema(), key, descriptor),
    getPrototypeOf: () => Reflect.getPrototypeOf(schema()),
    // Refused (see above): returning false makes Object.freeze / preventExtensions throw a TypeError here, while the
    // target stays extensible so every other trap keeps its invariants.
    preventExtensions: () => false,
    isExtensible: (target) => Reflect.isExtensible(target),
  })
}
