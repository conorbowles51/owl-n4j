// Every address key the review queue reads its view from. Whoever opens the queue anew (a batch's queue, Next to fix,
// a section change) clears all of them, so a filter picked earlier (an issue, a list) never narrows a queue opened
// later without being shown as chosen.
export const QUEUE_KEYS = [
  "queueItem", "queueList", "queueFiles", "queueBatch", "queueIssue", "queueSelection", "queueSelectionFiles",
] as const
