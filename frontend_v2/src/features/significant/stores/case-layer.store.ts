import { create } from "zustand"
import { persist } from "zustand/middleware"
import type { CaseLayer } from "../types"

interface CaseLayerState {
  layerByCase: Record<string, CaseLayer>
  setLayer: (caseId: string, layer: CaseLayer) => void
}

export const useCaseLayerStore = create<CaseLayerState>()(
  persist(
    (set) => ({
      layerByCase: {},
      setLayer: (caseId, layer) =>
        set((state) => ({
          layerByCase: { ...state.layerByCase, [caseId]: layer },
        })),
    }),
    {
      name: "loupe-case-layers-v1",
      partialize: (state) => ({ layerByCase: state.layerByCase }),
    }
  )
)

export function useCaseLayer(caseId: string | undefined): CaseLayer {
  return useCaseLayerStore((state) =>
    caseId ? (state.layerByCase[caseId] ?? "all") : "all"
  )
}
