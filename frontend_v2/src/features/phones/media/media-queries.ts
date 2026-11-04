import { getMediaIndex, getMediaWindow, type MediaFilter } from "../api"

/** Media items asked for per window of the grid. */
export const WINDOW = 200
/** The category or state value standing for "none set". */
export const NONE = "__none__"

/** The grid's filter: the phone, plus the thread, category and state chosen (MediaPage and the start-up prefetch). */
export function mediaFilter(caseId: string, extraction: string, thread: string | null, category: string, state: string): MediaFilter {
  return {
    case_id: caseId,
    phones: [extraction],
    ...(thread ? { thread_key: thread } : {}),
    ...(category ? { categories: [category === NONE ? "" : category] } : {}),
    ...(state ? { verification: [state === NONE ? "" : state] } : {}),
  }
}

/** Keys and fetchers shared by MediaPage and the start-up prefetch (route-data.ts). */
export const mediaIndexQuery = (filter: MediaFilter) => ({
  queryKey: ["phone-media-index", filter],
  queryFn: () => getMediaIndex(filter),
})

export const mediaPhoneIndexQuery = (caseId: string, extraction: string) => ({
  queryKey: ["phone-media-index", caseId, extraction],
  queryFn: () => getMediaIndex({ case_id: caseId, phones: [extraction] }),
})

export const mediaWindowQuery = (filter: MediaFilter) => ({
  queryKey: ["phone-media-window", filter],
  queryFn: ({ pageParam }: { pageParam: number }) => getMediaWindow(filter, pageParam, WINDOW),
  initialPageParam: 0,
  getNextPageParam: (last: Awaited<ReturnType<typeof getMediaWindow>>) =>
    last.items.length === WINDOW ? last.offset + WINDOW : undefined,
})
