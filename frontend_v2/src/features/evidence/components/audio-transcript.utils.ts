import type { TranscriptSegment } from "@/types/evidence.types"

export interface TranscriptSpeakerGroup {
  canonicalSpeaker: string
  displayName: string
  members: string[]
  turns: number
  duration: number
}

export function findActiveSegmentIndex(
  segments: TranscriptSegment[],
  currentTime: number
): number {
  if (segments.length === 0) return -1
  const exact = segments.findIndex(
    (segment) => currentTime >= segment.start && currentTime < segment.end
  )
  if (exact >= 0) return exact
  for (let index = segments.length - 1; index >= 0; index -= 1) {
    if (currentTime >= segments[index].start) return index
  }
  return -1
}

export function getDefaultSpeakerNames(segments: TranscriptSegment[]) {
  const names = new Map<string, string>()
  for (const segment of segments) {
    if (!names.has(segment.speaker)) {
      names.set(segment.speaker, `Speaker ${names.size + 1}`)
    }
  }
  return names
}

export function resolveCanonicalSpeaker(
  speaker: string,
  merges: Record<string, string>
): string {
  let current = speaker
  const visited = new Set<string>()

  while (merges[current] && !visited.has(current)) {
    visited.add(current)
    current = merges[current]
  }

  return current
}

export function mergeSpeakerGroups(
  segments: TranscriptSegment[],
  merges: Record<string, string>,
  sourceSpeaker: string,
  targetSpeaker: string
): Record<string, string> {
  const source = resolveCanonicalSpeaker(sourceSpeaker, merges)
  const target = resolveCanonicalSpeaker(targetSpeaker, merges)
  if (source === target) return merges

  const knownSpeakers = Array.from(
    new Set(segments.map((segment) => segment.speaker))
  )
  const nextMerges: Record<string, string> = {}

  for (const rawSpeaker of knownSpeakers) {
    const currentCanonical = resolveCanonicalSpeaker(rawSpeaker, merges)
    const nextCanonical = currentCanonical === source ? target : currentCanonical
    if (rawSpeaker !== nextCanonical) {
      nextMerges[rawSpeaker] = nextCanonical
    }
  }

  return nextMerges
}

export function unmergeSpeaker(
  merges: Record<string, string>,
  rawSpeaker: string
): Record<string, string> {
  const nextMerges = { ...merges }
  delete nextMerges[rawSpeaker]
  return nextMerges
}

export function getTranscriptSpeakerGroups(
  segments: TranscriptSegment[],
  speakers: Record<string, string>,
  merges: Record<string, string>,
  fallbackNames = getDefaultSpeakerNames(segments)
): TranscriptSpeakerGroup[] {
  const groups = new Map<string, TranscriptSpeakerGroup>()

  for (const segment of segments) {
    const canonicalSpeaker = resolveCanonicalSpeaker(segment.speaker, merges)
    let group = groups.get(canonicalSpeaker)
    if (!group) {
      group = {
        canonicalSpeaker,
        displayName:
          speakers[canonicalSpeaker] ||
          fallbackNames.get(canonicalSpeaker) ||
          canonicalSpeaker,
        members: [],
        turns: 0,
        duration: 0,
      }
      groups.set(canonicalSpeaker, group)
    }
    if (!group.members.includes(segment.speaker)) {
      group.members.push(segment.speaker)
    }
    group.turns += 1
    group.duration += Math.max(0, segment.end - segment.start)
  }

  return Array.from(groups.values())
}
