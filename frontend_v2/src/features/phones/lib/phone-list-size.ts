/**
 * The size of a phone list (Conversations' messages, the Timeline's phone entries).
 *
 * Below 768 px the page is one scrolling column, where a flex-1 list has no height and draws no rows: the list keeps
 * three quarters of the screen (Conversations, lx-corrorest 17 Nov; the Timeline, lx-leads 18 Nov, 0 rows at 390).
 * From 768 px up the list fills its column but never drops under 24rem: with the phone layers on, the controls above
 * it left the Conversations list 68 px and the Timeline's 0 px at 1500 x 950 (lx-leads 18 Nov); the column scrolls
 * instead (PHONE_LIST_COLUMN).
 */
export const PHONE_LIST_SIZE = "max-md:h-[75dvh] max-md:flex-none md:min-h-[24rem]"

/** The column that holds a phone list and its controls: it scrolls when they need more room than it has. */
export const PHONE_LIST_COLUMN = "overflow-y-auto"
