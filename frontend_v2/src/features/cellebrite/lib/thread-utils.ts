import type { CommsThread } from "../types"

function text(value: unknown) {
  return typeof value === "string" ? value : value == null ? "" : String(value)
}

function participantKeys(thread: CommsThread) {
  return (thread.participants ?? [])
    .map((participant) => text(participant?.key || participant?.identifier || participant?.phone))
    .filter(Boolean)
    .sort()
}

function contextKey(thread: CommsThread) {
  return [
    text(thread.report_key || thread.device_report_key),
    text(thread.source_app).toLowerCase(),
    text(thread.thread_type).toLowerCase(),
  ].join("::")
}

function exactKey(thread: CommsThread) {
  return `${contextKey(thread)}::${participantKeys(thread).join("|")}`
}

function newest(thread: CommsThread) {
  const raw = text(thread.last_activity || thread.timestamp)
  const time = raw ? new Date(raw).getTime() : 0
  return Number.isNaN(time) ? 0 : time
}

function score(thread: CommsThread) {
  return [
    Number(thread.message_count || thread.item_count || 0),
    thread.participants?.length ?? 0,
    newest(thread),
  ] as const
}

function pickBest(threads: CommsThread[]) {
  const sorted = [...threads].sort((left, right) => {
    const a = score(left)
    const b = score(right)
    return b[0] - a[0] || b[1] - a[1] || b[2] - a[2]
  })
  const winner = { ...sorted[0] }
  const merged = sorted
    .slice(1)
    .flatMap((thread) => [
      thread.thread_id,
      ...((thread.merged_thread_ids as string[] | undefined) ?? []),
    ])
    .filter(Boolean)
  if (merged.length) winner.merged_thread_ids = merged
  return winner
}

function isStrictSubset(left: Set<string>, right: Set<string>) {
  if (left.size === 0 || left.size >= right.size) return false
  for (const item of left) {
    if (!right.has(item)) return false
  }
  return true
}

export function dedupeCommsThreads(threads: CommsThread[] = []) {
  if (threads.length < 2) return threads

  const buckets = new Map<string, CommsThread[]>()
  for (const thread of threads) {
    const key = exactKey(thread)
    const bucket = buckets.get(key)
    if (bucket) bucket.push(thread)
    else buckets.set(key, [thread])
  }

  const survivors = [...buckets.values()].map(pickBest)
  const dropped = new Set<number>()

  for (let leftIndex = 0; leftIndex < survivors.length; leftIndex += 1) {
    if (dropped.has(leftIndex)) continue
    const left = survivors[leftIndex]
    const leftSet = new Set(participantKeys(left))

    for (let rightIndex = 0; rightIndex < survivors.length; rightIndex += 1) {
      if (leftIndex === rightIndex || dropped.has(rightIndex)) continue
      const right = survivors[rightIndex]
      if (contextKey(left) !== contextKey(right)) continue

      const rightSet = new Set(participantKeys(right))
      if (!isStrictSubset(leftSet, rightSet)) continue

      const merged = [
        ...((right.merged_thread_ids as string[] | undefined) ?? []),
        left.thread_id,
        ...((left.merged_thread_ids as string[] | undefined) ?? []),
      ].filter(Boolean)
      right.merged_thread_ids = Array.from(new Set(merged))
      dropped.add(leftIndex)
      break
    }
  }

  return survivors.filter((_, index) => !dropped.has(index))
}
