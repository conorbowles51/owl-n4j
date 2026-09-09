import { beforeEach, describe, expect, it } from "vitest"
import { useTableStore } from "./table.store"

describe("table.store entity type selection", () => {
  beforeEach(() => {
    useTableStore.getState().reset()
  })

  it("supports deselecting all and then selecting one type", () => {
    const availableTypes = ["Person", "Location"]

    expect(useTableStore.getState().selectedTypes).toBeNull()

    useTableStore.getState().clearTypes()
    expect(useTableStore.getState().selectedTypes).toEqual(new Set())

    useTableStore.getState().toggleType("Person", availableTypes)
    expect(useTableStore.getState().selectedTypes).toEqual(new Set(["Person"]))

    useTableStore.getState().selectAllTypes()
    expect(useTableStore.getState().selectedTypes).toBeNull()
  })
})
