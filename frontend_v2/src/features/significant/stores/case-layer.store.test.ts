import { beforeEach, describe, expect, it, vi } from "vitest"
import { useCaseLayerStore } from "./case-layer.store"

vi.hoisted(() => {
  const storedValues = new Map<string, string>()
  Object.defineProperty(globalThis, "localStorage", {
    configurable: true,
    value: {
      get length() {
        return storedValues.size
      },
      clear: () => storedValues.clear(),
      getItem: (key: string) => storedValues.get(key) ?? null,
      key: (index: number) => Array.from(storedValues.keys())[index] ?? null,
      removeItem: (key: string) => storedValues.delete(key),
      setItem: (key: string, value: string) => storedValues.set(key, value),
    } satisfies Storage,
  })
})

describe("case layer store", () => {
  beforeEach(() => {
    localStorage.clear()
    useCaseLayerStore.setState({ layerByCase: {} })
  })

  it("keeps one shared layer choice for every view in a case", () => {
    useCaseLayerStore.getState().setLayer("case-1", "significant")

    expect(useCaseLayerStore.getState().layerByCase["case-1"]).toBe("significant")
    expect(useCaseLayerStore.getState().layerByCase["case-2"]).toBeUndefined()
  })

  it("can return a case to the complete dataset", () => {
    useCaseLayerStore.getState().setLayer("case-1", "significant")
    useCaseLayerStore.getState().setLayer("case-1", "all")

    expect(useCaseLayerStore.getState().layerByCase["case-1"]).toBe("all")
  })
})
