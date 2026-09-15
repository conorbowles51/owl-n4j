import { create } from "zustand"
import { createJSONStorage, persist } from "zustand/middleware"
import { z } from "zod"

const locationSchema = z.object({
  selections: z
    .record(
      z.string(),
      z.object({ fileId: z.string().nullable(), open: z.boolean() })
    )
    .default({}),
  pages: z.record(z.string(), z.number().int().positive()).default({}),
  reviewChoices: z
    .record(
      z.string(),
      z.object({ currency: z.string(), statementId: z.string() })
    )
    .default({}),
  sectionSearches: z.record(z.string(), z.string()).default({}),
})
type Location = z.infer<typeof locationSchema>
type Workspace = Location & {
  setPage: (scope: string, page: number) => void
  setReviewChoice: (
    scope: string,
    changes: Partial<{ currency: string; statementId: string }>
  ) => void
  setSectionSearch: (scope: string, search: string) => void
  select: (scope: string, fileId: string | null) => void
  setOpen: (scope: string, open: boolean) => void
}

// Keys include the signed-in user and case. Store only navigation values here;
// statement corrections have their own revision-bound drafts.
export const useStatementWorkspace = create<Workspace>()(
  persist(
    (set) => ({
      selections: {},
      pages: {},
      reviewChoices: {},
      sectionSearches: {},
      setPage: (scope, page) =>
        set((state) => ({ pages: { ...state.pages, [scope]: page } })),
      setReviewChoice: (scope, changes) =>
        set((state) => ({
          reviewChoices: {
            ...state.reviewChoices,
            [scope]: {
              ...(state.reviewChoices[scope] ?? {
                currency: "",
                statementId: "",
              }),
              ...changes,
            },
          },
        })),
      setSectionSearch: (scope, search) =>
        set((state) => ({
          sectionSearches: { ...state.sectionSearches, [scope]: search },
        })),
      select: (scope, fileId) =>
        set((state) => ({
          selections: { ...state.selections, [scope]: { fileId, open: true } },
        })),
      setOpen: (scope, open) =>
        set((state) => ({
          selections: {
            ...state.selections,
            [scope]: { fileId: state.selections[scope]?.fileId ?? null, open },
          },
        })),
    }),
    {
      name: "loupe-statement-workspace",
      version: 1,
      storage: createJSONStorage(() => sessionStorage),
      partialize: (state) => ({
        selections: state.selections,
        pages: state.pages,
        reviewChoices: state.reviewChoices,
        sectionSearches: state.sectionSearches,
      }),
      merge: (stored, current) => {
        const parsed = locationSchema.safeParse(stored)
        return parsed.success ? { ...current, ...parsed.data } : current
      },
    }
  )
)
