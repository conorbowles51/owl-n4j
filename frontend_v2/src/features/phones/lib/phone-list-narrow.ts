/**
 * A phone list's size below 768 px. There its page is one scrolling column, where a flex-1 list has no height and
 * draws no rows; the list keeps three quarters of the screen instead (Conversations, lx-corrorest 17 Nov; the
 * Timeline's phone entries, lx-leads 18 Nov, which drew 0 rows at 390 wide).
 */
export const PHONE_LIST_NARROW = "max-md:h-[75dvh] max-md:flex-none"
