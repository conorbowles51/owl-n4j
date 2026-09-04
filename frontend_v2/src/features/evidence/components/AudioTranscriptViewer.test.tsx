import { render, waitFor } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import {
  findActiveSegmentIndex,
  getDefaultSpeakerNames,
  getTranscriptSpeakerGroups,
  mergeSpeakerGroups,
  resolveCanonicalSpeaker,
  unmergeSpeaker,
} from "./audio-transcript.utils"
import type { TranscriptSegment } from "@/types/evidence.types"
import { AudioTranscriptViewer } from "./AudioTranscriptViewer"

const segments: TranscriptSegment[] = [
  { id: "a", start: 1.5, end: 4, speaker: "A", text: "First turn" },
  { id: "b", start: 4.8, end: 8, speaker: "B", text: "Second turn" },
  { id: "c", start: 8.2, end: 9.2, speaker: "C", text: "Short turn" },
  { id: "d", start: 9.4, end: 11, speaker: "A", text: "Fourth turn" },
]

describe("findActiveSegmentIndex", () => {
  it("tracks the current turn and holds the preceding turn across short gaps", () => {
    expect(findActiveSegmentIndex(segments, 0)).toBe(-1)
    expect(findActiveSegmentIndex(segments, 2)).toBe(0)
    expect(findActiveSegmentIndex(segments, 4.4)).toBe(0)
    expect(findActiveSegmentIndex(segments, 6)).toBe(1)
  })
})

describe("citation navigation", () => {
  it("seeks an audio transcript to the cited starting time", async () => {
    const { container } = render(
      <AudioTranscriptViewer
        segments={segments}
        initialTime={8.2}
      />,
    )
    const audio = container.querySelector("audio")
    expect(audio).not.toBeNull()
    await waitFor(() => expect(audio?.currentTime).toBe(8.2))
  })
})

describe("transcript speaker merges", () => {
  it("combines all source turns into a target identity without changing segments", () => {
    const fallbackNames = getDefaultSpeakerNames(segments)
    const merges = mergeSpeakerGroups(segments, {}, "C", "A")
    const groups = getTranscriptSpeakerGroups(
      segments,
      { A: "Caller" },
      merges,
      fallbackNames
    )

    expect(merges).toEqual({ C: "A" })
    expect(resolveCanonicalSpeaker("C", merges)).toBe("A")
    expect(groups).toHaveLength(2)
    expect(groups[0]).toMatchObject({
      canonicalSpeaker: "A",
      displayName: "Caller",
      members: ["A", "C"],
      turns: 3,
    })
    expect(segments[2].speaker).toBe("C")
  })

  it("flattens group-to-group merges and can restore one raw label", () => {
    const firstMerge = mergeSpeakerGroups(segments, {}, "C", "A")
    const secondMerge = mergeSpeakerGroups(
      segments,
      firstMerge,
      "A",
      "B"
    )

    expect(secondMerge).toEqual({ A: "B", C: "B" })
    expect(unmergeSpeaker(secondMerge, "C")).toEqual({ A: "B" })
  })
})
