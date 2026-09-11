import { create } from "zustand"

type Selection = { fileId: string | null; open: boolean }
type Workspace = {
  selections: Record<string, Selection>
  pages: Record<string, number>
  setPage: (scope: string, page: number) => void
  reviewChoices: Record<string, { currency: string; statementId: string }>
  setReviewChoice: (
    scope: string,
    changes: Partial<{ currency: string; statementId: string }>
  ) => void
  select: (scope: string, fileId: string | null) => void
  setOpen: (scope: string, open: boolean) => void
}

export const useStatementWorkspace = create<Workspace>((set) => ({
  selections: {},
  pages: {},
  setPage: (scope, page) =>
    set((state) => ({ pages: { ...state.pages, [scope]: page } })),
  reviewChoices: {},
  setReviewChoice: (scope, changes) =>
    set((state) => ({
      reviewChoices: {
        ...state.reviewChoices,
        [scope]: {
          ...(state.reviewChoices[scope] ?? { currency: "", statementId: "" }),
          ...changes,
        },
      },
    })),
  select: (scope, fileId) =>
    set((state) => ({
      selections: {
        ...state.selections,
        [scope]: { fileId, open: true },
      },
    })),
  setOpen: (scope, open) =>
    set((state) => ({
      selections: {
        ...state.selections,
        [scope]: { fileId: state.selections[scope]?.fileId ?? null, open },
      },
    })),
}))
