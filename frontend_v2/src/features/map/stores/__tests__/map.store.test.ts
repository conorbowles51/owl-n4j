import { beforeEach, describe, expect, it } from "vitest"
import { useMapStore } from "../map.store"

function addDraftTriangle(offset = 0) {
  const store = useMapStore.getState()
  store.addDrawingPoint([offset, offset])
  store.addDrawingPoint([offset + 1, offset])
  store.addDrawingPoint([offset, offset + 1])
  store.finishDrawingShape()
}

function addAppliedTriangle(offset = 0) {
  addDraftTriangle(offset)
  useMapStore.getState().applyBoundingShapeFilter()
}

describe("map.store", () => {
  beforeEach(() => {
    useMapStore.getState().reset()
  })

  describe("bounding shape drawing", () => {
    it("toggles draw mode and clears an in-progress shape when turned off", () => {
      useMapStore.getState().toggleDrawMode()
      expect(useMapStore.getState().drawMode).toBe(true)

      useMapStore.getState().addDrawingPoint([1, 1])
      useMapStore.getState().toggleDrawMode()

      expect(useMapStore.getState().drawMode).toBe(false)
      expect(useMapStore.getState().drawingPoints).toEqual([])
    })

    it("adds points and undoes the last drawing point", () => {
      const store = useMapStore.getState()
      store.addDrawingPoint([1, 1])
      store.addDrawingPoint([2, 2])

      useMapStore.getState().undoLastDrawingPoint()

      expect(useMapStore.getState().drawingPoints).toEqual([[1, 1]])
    })

    it("does not finish a shape with fewer than three points", () => {
      const store = useMapStore.getState()
      store.addDrawingPoint([1, 1])
      store.addDrawingPoint([2, 2])
      store.finishDrawingShape()

      expect(useMapStore.getState().boundingShapes).toEqual([])
      expect(useMapStore.getState().draftBoundingShapes).toEqual([])
      expect(useMapStore.getState().drawingPoints).toEqual([
        [1, 1],
        [2, 2],
      ])
    })

    it("finishes a shape as a draft and stays in draw mode", () => {
      useMapStore.getState().toggleDrawMode()
      addDraftTriangle()

      const state = useMapStore.getState()
      expect(state.drawMode).toBe(true)
      expect(state.drawingPoints).toEqual([])
      expect(state.boundingShapes).toEqual([])
      expect(state.draftBoundingShapes).toHaveLength(1)
      expect(state.draftBoundingShapes[0].coordinates).toEqual([
        [0, 0],
        [1, 0],
        [0, 1],
        [0, 0],
      ])
    })

    it("applies drafts to committed bounding shapes", () => {
      addDraftTriangle()
      addDraftTriangle(10)

      useMapStore.getState().applyBoundingShapeFilter()

      const state = useMapStore.getState()
      expect(state.draftBoundingShapes).toEqual([])
      expect(state.boundingShapes).toHaveLength(2)
    })

    it("removes one draft shape by id", () => {
      addDraftTriangle()
      addDraftTriangle(10)

      const [first, second] = useMapStore.getState().draftBoundingShapes
      if (!first || !second) throw new Error("expected two draft shapes")

      useMapStore.getState().removeDraftBoundingShape(first.id)

      expect(useMapStore.getState().draftBoundingShapes).toEqual([second])
    })

    it("discards pending draft shapes and drawing points", () => {
      addDraftTriangle()
      useMapStore.getState().addDrawingPoint([99, 99])

      useMapStore.getState().discardBoundingShapeDraft()

      expect(useMapStore.getState().drawingPoints).toEqual([])
      expect(useMapStore.getState().draftBoundingShapes).toEqual([])
      expect(useMapStore.getState().boundingShapes).toEqual([])
    })

    it("removes one committed shape by id", () => {
      addAppliedTriangle()
      addAppliedTriangle(10)

      const [first, second] = useMapStore.getState().boundingShapes
      if (!first || !second) throw new Error("expected two shapes")

      useMapStore.getState().removeBoundingShape(first.id)

      expect(useMapStore.getState().boundingShapes).toEqual([second])
    })

    it("clears committed shapes", () => {
      addAppliedTriangle()

      useMapStore.getState().clearBoundingShapes()

      expect(useMapStore.getState().boundingShapes).toEqual([])
    })

    it("reset clears draw mode, drawing points, and committed shapes", () => {
      useMapStore.getState().toggleDrawMode()
      useMapStore.getState().addDrawingPoint([1, 1])
      addDraftTriangle()
      useMapStore.getState().applyBoundingShapeFilter()
      addDraftTriangle(10)

      useMapStore.getState().reset()

      expect(useMapStore.getState().drawMode).toBe(false)
      expect(useMapStore.getState().drawingPoints).toEqual([])
      expect(useMapStore.getState().draftBoundingShapes).toEqual([])
      expect(useMapStore.getState().boundingShapes).toEqual([])
    })
  })
})
