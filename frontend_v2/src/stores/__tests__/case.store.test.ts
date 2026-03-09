import { describe, it, expect, beforeEach } from "vitest"
import { useCaseStore } from "../case.store"

describe("case.store", () => {
  beforeEach(() => {
    useCaseStore.setState({
      currentCaseId: null,
      currentCaseName: null,
      currentCaseVersion: null,
    })
  })

  it("has null initial state", () => {
    const state = useCaseStore.getState()
    expect(state.currentCaseId).toBeNull()
    expect(state.currentCaseName).toBeNull()
    expect(state.currentCaseVersion).toBeNull()
  })

  it("setActiveCase sets all fields", () => {
    useCaseStore.getState().setActiveCase("case-1", "Test Case", "v2")
    const state = useCaseStore.getState()
    expect(state.currentCaseId).toBe("case-1")
    expect(state.currentCaseName).toBe("Test Case")
    expect(state.currentCaseVersion).toBe("v2")
  })

  it("setActiveCase defaults version to null", () => {
    useCaseStore.getState().setActiveCase("case-1", "Test Case")
    expect(useCaseStore.getState().currentCaseVersion).toBeNull()
  })

  it("clearActiveCase resets all fields", () => {
    useCaseStore.getState().setActiveCase("case-1", "Test Case", "v1")
    useCaseStore.getState().clearActiveCase()
    const state = useCaseStore.getState()
    expect(state.currentCaseId).toBeNull()
    expect(state.currentCaseName).toBeNull()
    expect(state.currentCaseVersion).toBeNull()
  })
})
