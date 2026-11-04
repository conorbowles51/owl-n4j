import { getMediaIndex, getMediaWindow, type MediaFilter } from "../api"

/** Media items asked for per window of the grid. */
export const WINDOW = 200
/** The category or state value standing for "none set". */
export const NONE = "__none__"

/** Every phone in the case, in place of one phone's id. */
export const EVERY_PHONE = "*"

/**
 * The grid's filter: the phone (or EVERY_PHONE), plus the thread, category and state chosen and, in `more`, only the
 * app, person and date filters that are set (MediaPage and the start-up prefetch, which share one cache entry).
 */
export function mediaFilter(caseId: string, extraction: string, thread: string | null, category: string, state: string,
  more: Pick<MediaFilter, "apps" | "participants" | "from_instant" | "to_instant" | "significant_only"> = {}): MediaFilter {
  return {
    case_id: caseId,
    ...(extraction === EVERY_PHONE ? {} : { phones: [extraction] }),
    ...(thread ? { thread_key: thread } : {}),
    ...(category ? { categories: [category === NONE ? "" : category] } : {}),
    ...(state ? { verification: [state === NONE ? "" : state] } : {}),
    ...more,
  }
}

/** Keys and fetchers shared by MediaPage and the start-up prefetch (route-data.ts). */
export const mediaIndexQuery = (filter: MediaFilter) => ({
  queryKey: ["phone-media-index", filter],
  queryFn: () => getMediaIndex(filter),
})

export const mediaPhoneIndexQuery = (caseId: string, extraction: string) => ({
  queryKey: ["phone-media-index", caseId, extraction],
  queryFn: () => getMediaIndex(mediaFilter(caseId, extraction, null, "", "")),
})

export const mediaWindowQuery = (filter: MediaFilter) => ({
  queryKey: ["phone-media-window", filter],
  queryFn: ({ pageParam }: { pageParam: number }) => getMediaWindow(filter, pageParam, WINDOW),
  initialPageParam: 0,
  getNextPageParam: (last: Awaited<ReturnType<typeof getMediaWindow>>) =>
    last.items.length === WINDOW ? last.offset + WINDOW : undefined,
})
