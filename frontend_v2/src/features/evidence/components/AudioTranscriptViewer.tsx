import { useEffect, useMemo, useRef, useState } from "react"
import {
  Check,
  ChevronDown,
  ChevronUp,
  CircleDot,
  Gauge,
  Pause,
  Pencil,
  Play,
  RotateCcw,
  RotateCw,
  Search,
  Users,
  X,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { cn } from "@/lib/cn"
import type {
  TranscriptSegment,
  TranscriptSpeakerSettings,
} from "@/types/evidence.types"
import {
  findActiveSegmentIndex,
  getDefaultSpeakerNames,
  getTranscriptSpeakerGroups,
  mergeSpeakerGroups,
  resolveCanonicalSpeaker,
  unmergeSpeaker,
} from "./audio-transcript.utils"
import { TranscriptSpeakerManager } from "./TranscriptSpeakerManager"

interface AudioTranscriptViewerProps {
  audioUrl?: string
  documentName?: string
  transcription?: string | null
  segments?: TranscriptSegment[]
  speakers?: Record<string, string>
  speakerMerges?: Record<string, string>
  onSpeakerSettingsChange?: (
    settings: TranscriptSpeakerSettings
  ) => Promise<TranscriptSpeakerSettings | void>
  onCanPlay?: () => void
  onError?: () => void
}

function formatTime(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) return "00:00"
  const rounded = Math.floor(seconds)
  const hours = Math.floor(rounded / 3600)
  const minutes = Math.floor((rounded % 3600) / 60)
  const secs = rounded % 60
  return hours > 0
    ? `${hours}:${String(minutes).padStart(2, "0")}:${String(secs).padStart(2, "0")}`
    : `${String(minutes).padStart(2, "0")}:${String(secs).padStart(2, "0")}`
}

function HighlightedText({ text, query }: { text: string; query: string }) {
  const normalized = query.trim().toLocaleLowerCase()
  if (!normalized) return text

  const parts: React.ReactNode[] = []
  const lowerText = text.toLocaleLowerCase()
  let cursor = 0
  let match = lowerText.indexOf(normalized)
  while (match >= 0) {
    if (match > cursor) parts.push(text.slice(cursor, match))
    parts.push(
      <mark
        key={`${match}-${cursor}`}
        className="rounded-sm bg-amber-300/70 px-0.5 text-stone-950 dark:bg-amber-400/70"
      >
        {text.slice(match, match + normalized.length)}
      </mark>
    )
    cursor = match + normalized.length
    match = lowerText.indexOf(normalized, cursor)
  }
  if (cursor < text.length) parts.push(text.slice(cursor))
  return parts
}

export function AudioTranscriptViewer({
  audioUrl,
  documentName,
  transcription,
  segments = [],
  speakers = {},
  speakerMerges = {},
  onSpeakerSettingsChange,
  onCanPlay,
  onError,
}: AudioTranscriptViewerProps) {
  const audioRef = useRef<HTMLAudioElement>(null)
  const segmentRefs = useRef<Array<HTMLDivElement | null>>([])
  const [currentTime, setCurrentTime] = useState(0)
  const [duration, setDuration] = useState(0)
  const [playing, setPlaying] = useState(false)
  const [playbackRate, setPlaybackRate] = useState(1)
  const [query, setQuery] = useState("")
  const [matchPosition, setMatchPosition] = useState(0)
  const [followPlayback, setFollowPlayback] = useState(true)
  const [editingSpeaker, setEditingSpeaker] = useState<string | null>(null)
  const [editingSegmentIndex, setEditingSegmentIndex] = useState<number | null>(null)
  const [speakerDraft, setSpeakerDraft] = useState("")
  const [workingSpeakers, setWorkingSpeakers] = useState(speakers)
  const [workingMerges, setWorkingMerges] = useState(speakerMerges)
  const [savingSpeaker, setSavingSpeaker] = useState(false)

  const fallbackNames = useMemo(
    () => getDefaultSpeakerNames(segments),
    [segments]
  )
  const speakerGroups = useMemo(
    () =>
      getTranscriptSpeakerGroups(
        segments,
        workingSpeakers,
        workingMerges,
        fallbackNames
      ),
    [fallbackNames, segments, workingMerges, workingSpeakers]
  )
  const speakerGroupOrder = useMemo(
    () =>
      new Map(
        speakerGroups.map((group, index) => [
          group.canonicalSpeaker,
          index,
        ])
      ),
    [speakerGroups]
  )
  const activeSegmentIndex = useMemo(
    () => findActiveSegmentIndex(segments, currentTime),
    [currentTime, segments]
  )
  const matchIndices = useMemo(() => {
    const normalized = query.trim().toLocaleLowerCase()
    if (!normalized) return []
    return segments.flatMap((segment, index) =>
      segment.text.toLocaleLowerCase().includes(normalized) ? [index] : []
    )
  }, [query, segments])
  const transcriptDuration = segments.reduce(
    (longest, segment) => Math.max(longest, segment.end),
    0
  )
  const timelineDuration = duration || transcriptDuration

  useEffect(() => {
    setWorkingSpeakers(speakers)
  }, [speakers])

  useEffect(() => {
    setWorkingMerges(speakerMerges)
  }, [speakerMerges])

  useEffect(() => {
    setMatchPosition(0)
  }, [query])

  useEffect(() => {
    if (!followPlayback || activeSegmentIndex < 0) return
    segmentRefs.current[activeSegmentIndex]?.scrollIntoView?.({
      block: "center",
      behavior: playing ? "smooth" : "auto",
    })
  }, [activeSegmentIndex, followPlayback, playing])

  const canonicalSpeaker = (speaker: string) =>
    resolveCanonicalSpeaker(speaker, workingMerges)

  const speakerName = (speaker: string) => {
    const canonical = canonicalSpeaker(speaker)
    return (
      workingSpeakers[canonical] ||
      fallbackNames.get(canonical) ||
      canonical
    )
  }

  const seek = (seconds: number) => {
    if (!audioRef.current) return
    const nextTime = Math.min(
      Math.max(seconds, 0),
      Number.isFinite(audioRef.current.duration) && audioRef.current.duration > 0
        ? audioRef.current.duration
        : Math.max(timelineDuration, seconds, 0)
    )
    audioRef.current.currentTime = nextTime
    setCurrentTime(nextTime)
  }

  const togglePlayback = async () => {
    const audio = audioRef.current
    if (!audio) return
    if (audio.paused) {
      await audio.play()
    } else {
      audio.pause()
    }
  }

  const navigateMatch = (direction: -1 | 1) => {
    if (matchIndices.length === 0) return
    const nextPosition =
      (matchPosition + direction + matchIndices.length) % matchIndices.length
    setMatchPosition(nextPosition)
    const segmentIndex = matchIndices[nextPosition]
    seek(segments[segmentIndex].start)
    segmentRefs.current[segmentIndex]?.scrollIntoView?.({
      block: "center",
      behavior: "smooth",
    })
  }

  const startEditingSpeaker = (speaker: string, segmentIndex: number) => {
    const canonical = canonicalSpeaker(speaker)
    setEditingSpeaker(canonical)
    setEditingSegmentIndex(segmentIndex)
    setSpeakerDraft(speakerName(canonical))
  }

  const persistSpeakerSettings = async (
    nextSpeakers: Record<string, string>,
    nextMerges: Record<string, string>
  ) => {
    if (!onSpeakerSettingsChange) return

    const previousSpeakers = workingSpeakers
    const previousMerges = workingMerges
    setSavingSpeaker(true)
    setWorkingSpeakers(nextSpeakers)
    setWorkingMerges(nextMerges)
    try {
      const saved = await onSpeakerSettingsChange({
        speakers: nextSpeakers,
        merges: nextMerges,
      })
      if (saved) {
        setWorkingSpeakers(saved.speakers)
        setWorkingMerges(saved.merges)
      }
    } catch (error) {
      setWorkingSpeakers(previousSpeakers)
      setWorkingMerges(previousMerges)
      throw error
    } finally {
      setSavingSpeaker(false)
    }
  }

  const renameSpeaker = async (speaker: string, name: string) => {
    const trimmed = name.trim()
    const nextSpeakers = { ...workingSpeakers }
    const defaultName = fallbackNames.get(speaker)
    if (!trimmed || trimmed === defaultName) {
      delete nextSpeakers[speaker]
    } else {
      nextSpeakers[speaker] = trimmed
    }
    await persistSpeakerSettings(nextSpeakers, workingMerges)
  }

  const saveSpeaker = async () => {
    if (!editingSpeaker || !onSpeakerSettingsChange) {
      setEditingSpeaker(null)
      setEditingSegmentIndex(null)
      return
    }
    try {
      await renameSpeaker(editingSpeaker, speakerDraft)
      setEditingSpeaker(null)
      setEditingSegmentIndex(null)
    } catch {
      // The parent callback reports the persistence error.
    }
  }

  const mergeSpeakers = async (
    sourceSpeaker: string,
    targetSpeaker: string,
    combinedName: string
  ) => {
    const target = canonicalSpeaker(targetSpeaker)
    const nextMerges = mergeSpeakerGroups(
      segments,
      workingMerges,
      sourceSpeaker,
      target
    )
    const nextSpeakers = { ...workingSpeakers }
    const trimmed = combinedName.trim()
    if (!trimmed || trimmed === fallbackNames.get(target)) {
      delete nextSpeakers[target]
    } else {
      nextSpeakers[target] = trimmed
    }
    await persistSpeakerSettings(nextSpeakers, nextMerges)
  }

  const restoreSpeaker = async (rawSpeaker: string) => {
    await persistSpeakerSettings(
      workingSpeakers,
      unmergeSpeaker(workingMerges, rawSpeaker)
    )
  }

  const activeSpeaker =
    activeSegmentIndex >= 0 ? speakerName(segments[activeSegmentIndex].speaker) : null

  return (
    <div className="grid h-full min-h-0 grid-cols-[minmax(250px,0.34fr)_minmax(0,0.66fr)] bg-stone-950 text-stone-100">
      <section className="relative flex min-h-0 flex-col overflow-hidden border-r border-white/10">
        <div className="absolute inset-0 opacity-40 [background-image:radial-gradient(circle_at_20%_10%,rgba(245,158,11,0.24),transparent_38%),linear-gradient(145deg,transparent_42%,rgba(255,255,255,0.035)_42%,rgba(255,255,255,0.035)_43%,transparent_43%)]" />
        <div className="relative flex flex-1 flex-col justify-between p-6">
          <div>
            <div className="mb-8 flex items-center justify-between">
              <div className="flex items-center gap-2 text-[10px] font-semibold uppercase tracking-[0.22em] text-amber-300/80">
                <CircleDot className="size-3.5" />
                Audio evidence
              </div>
              <span className="rounded-full border border-white/10 bg-white/5 px-2 py-1 text-[10px] text-stone-400">
                {segments.length > 0 ? "Speaker timed" : "Audio only"}
              </span>
            </div>

            <p className="line-clamp-2 text-lg font-semibold leading-snug text-white">
              {documentName || "Audio recording"}
            </p>
            <p className="mt-2 text-xs text-stone-500">
              {activeSpeaker ? `${activeSpeaker} is speaking` : "Ready to review"}
            </p>

            <div className="mt-10 rounded-xl border border-white/10 bg-black/20 px-4 py-3">
              <p className="mb-3 text-[9px] font-semibold uppercase tracking-[0.18em] text-stone-600">
                Conversation map
              </p>
              <div className="relative h-16 overflow-hidden">
                <div className="absolute left-0 right-0 top-1/2 h-px bg-white/10" />
                {segments.map((segment, index) => {
                  const mapDuration = Math.max(timelineDuration, 1)
                  const left = (segment.start / mapDuration) * 100
                  const width = Math.max(
                    ((segment.end - segment.start) / mapDuration) * 100,
                    0.6
                  )
                  const speakerOrder =
                    speakerGroupOrder.get(
                      canonicalSpeaker(segment.speaker)
                    ) ?? 0
                  const above = speakerOrder % 2 === 0
                  const elapsed = segment.start <= currentTime
                  return (
                    <button
                      key={segment.id || index}
                      type="button"
                      onClick={() => seek(segment.start)}
                      title={`${speakerName(segment.speaker)} at ${formatTime(segment.start)}`}
                      className={cn(
                        "absolute h-6 min-w-0.5 rounded-sm border transition-colors",
                        above ? "bottom-1/2 mb-1" : "top-1/2 mt-1",
                        elapsed
                          ? "border-amber-300/70 bg-amber-400/80"
                          : "border-stone-600 bg-stone-700 hover:bg-stone-600"
                      )}
                      style={{ left: `${left}%`, width: `${width}%` }}
                    />
                  )
                })}
                {segments.length === 0 && (
                  <div className="absolute left-0 right-0 top-1/2 flex -translate-y-1/2 gap-1">
                    {Array.from({ length: 24 }, (_, index) => (
                      <span key={index} className="h-1 flex-1 rounded-full bg-stone-700" />
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>

          <div className="space-y-4">
            <input
              aria-label="Recording position"
              type="range"
              min={0}
              max={timelineDuration || 0}
              step={0.1}
              value={Math.min(currentTime, timelineDuration || 0)}
              onChange={(event) => seek(Number(event.target.value))}
              className="h-1.5 w-full cursor-pointer accent-amber-400"
            />
            <div className="flex items-center justify-between font-mono text-[11px] text-stone-400">
              <span>{formatTime(currentTime)}</span>
              <span>{formatTime(timelineDuration)}</span>
            </div>
            <div className="flex items-center justify-center gap-3">
              <Button
                variant="ghost"
                size="icon"
                className="text-stone-300 hover:bg-white/10 hover:text-white"
                onClick={() => seek(currentTime - 10)}
                title="Back 10 seconds"
              >
                <RotateCcw className="size-4" />
              </Button>
              <Button
                size="icon"
                className="size-12 rounded-full bg-amber-400 text-stone-950 hover:bg-amber-300"
                onClick={() => void togglePlayback()}
                title={playing ? "Pause" : "Play"}
              >
                {playing ? <Pause className="size-5" /> : <Play className="ml-0.5 size-5" />}
              </Button>
              <Button
                variant="ghost"
                size="icon"
                className="text-stone-300 hover:bg-white/10 hover:text-white"
                onClick={() => seek(currentTime + 10)}
                title="Forward 10 seconds"
              >
                <RotateCw className="size-4" />
              </Button>
            </div>
            <div className="flex items-center justify-center gap-2 text-xs text-stone-400">
              <Gauge className="size-3.5" />
              {[0.75, 1, 1.25, 1.5, 2].map((rate) => (
                <button
                  key={rate}
                  type="button"
                  onClick={() => {
                    setPlaybackRate(rate)
                    if (audioRef.current) audioRef.current.playbackRate = rate
                  }}
                  className={cn(
                    "rounded px-1.5 py-1 transition-colors",
                    playbackRate === rate
                      ? "bg-white/10 text-amber-300"
                      : "hover:bg-white/5 hover:text-white"
                  )}
                >
                  {rate}×
                </button>
              ))}
            </div>
          </div>
        </div>

        <audio
          ref={audioRef}
          src={audioUrl}
          preload="metadata"
          onLoadedMetadata={(event) => {
            setDuration(event.currentTarget.duration || 0)
            onCanPlay?.()
          }}
          onCanPlay={onCanPlay}
          onTimeUpdate={(event) => setCurrentTime(event.currentTarget.currentTime)}
          onPlay={() => setPlaying(true)}
          onPause={() => setPlaying(false)}
          onEnded={() => setPlaying(false)}
          onError={onError}
        />
      </section>

      <section className="flex min-h-0 flex-col bg-stone-50 text-stone-900 dark:bg-stone-900 dark:text-stone-100">
        <header className="border-b border-stone-200 bg-white/90 px-5 py-4 backdrop-blur dark:border-white/10 dark:bg-stone-900/90">
          <div className="flex items-center justify-between gap-4">
            <div>
              <div className="flex items-center gap-2">
                <Users className="size-4 text-amber-600 dark:text-amber-400" />
                <h2 className="text-sm font-semibold">Synchronized transcript</h2>
              </div>
              <p className="mt-1 text-xs text-stone-500">
                Select a turn to jump to that point in the recording.
              </p>
            </div>
            <div className="flex shrink-0 items-center gap-2">
              {onSpeakerSettingsChange && speakerGroups.length > 0 && (
                <TranscriptSpeakerManager
                  groups={speakerGroups}
                  fallbackNames={fallbackNames}
                  saving={savingSpeaker}
                  onRename={renameSpeaker}
                  onMerge={mergeSpeakers}
                  onUnmerge={restoreSpeaker}
                />
              )}
              <Button
                variant={followPlayback ? "secondary" : "ghost"}
                size="sm"
                onClick={() => setFollowPlayback((value) => !value)}
                className="shrink-0 text-xs"
              >
                <CircleDot className="size-3.5" />
                {followPlayback ? "Following" : "Follow"}
              </Button>
            </div>
          </div>

          <div className="mt-4 flex items-center gap-2">
            <div className="relative min-w-0 flex-1">
              <Search className="absolute left-3 top-1/2 size-3.5 -translate-y-1/2 text-stone-400" />
              <Input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Search this transcript"
                className="h-9 bg-stone-50 pl-9 pr-9 text-sm dark:bg-black/20"
              />
              {query && (
                <button
                  type="button"
                  onClick={() => setQuery("")}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-stone-400 hover:text-stone-700 dark:hover:text-stone-200"
                  title="Clear search"
                >
                  <X className="size-3.5" />
                </button>
              )}
            </div>
            <span className="min-w-16 text-center text-[11px] tabular-nums text-stone-500">
              {query.trim()
                ? `${matchIndices.length ? matchPosition + 1 : 0} / ${matchIndices.length}`
                : `${segments.length} turns`}
            </span>
            <Button
              variant="outline"
              size="icon-sm"
              disabled={matchIndices.length === 0}
              onClick={() => navigateMatch(-1)}
              title="Previous match"
            >
              <ChevronUp className="size-3.5" />
            </Button>
            <Button
              variant="outline"
              size="icon-sm"
              disabled={matchIndices.length === 0}
              onClick={() => navigateMatch(1)}
              title="Next match"
            >
              <ChevronDown className="size-3.5" />
            </Button>
          </div>
        </header>

        <div className="min-h-0 flex-1 overflow-y-auto scroll-smooth px-5 py-5">
          {segments.length > 0 ? (
            <div className="mx-auto max-w-3xl space-y-2 pb-24">
              {segments.map((segment, index) => {
                const active = index === activeSegmentIndex
                const isMatch = matchIndices[matchPosition] === index
                const segmentCanonicalSpeaker = canonicalSpeaker(
                  segment.speaker
                )
                const isEditing =
                  editingSpeaker === segmentCanonicalSpeaker &&
                  editingSegmentIndex === index
                return (
                  <div
                    key={segment.id || `${segment.start}-${index}`}
                    ref={(element) => {
                      segmentRefs.current[index] = element
                    }}
                    className={cn(
                      "group grid grid-cols-[76px_minmax(0,1fr)] gap-3 rounded-lg border px-3 py-3 transition-all",
                      active
                        ? "border-amber-400/70 bg-amber-50 shadow-[inset_3px_0_0_0_rgb(245,158,11)] dark:bg-amber-400/10"
                        : isMatch
                          ? "border-amber-300/60 bg-amber-50/60 dark:bg-amber-400/5"
                          : "border-transparent hover:border-stone-200 hover:bg-white dark:hover:border-white/10 dark:hover:bg-white/5"
                    )}
                  >
                    <button
                      type="button"
                      onClick={() => seek(segment.start)}
                      className="pt-0.5 text-left font-mono text-[11px] tabular-nums text-stone-400 hover:text-amber-600"
                      title={`Jump to ${formatTime(segment.start)}`}
                    >
                      {formatTime(segment.start)}
                    </button>
                    <div className="min-w-0">
                      <div className="mb-1.5 flex min-h-6 items-center gap-1.5">
                        {isEditing ? (
                          <>
                            <Input
                              autoFocus
                              value={speakerDraft}
                              maxLength={80}
                              onChange={(event) => setSpeakerDraft(event.target.value)}
                              onKeyDown={(event) => {
                                if (event.key === "Enter") void saveSpeaker()
                                if (event.key === "Escape") {
                                  setEditingSpeaker(null)
                                  setEditingSegmentIndex(null)
                                }
                              }}
                              className="h-7 max-w-56 text-xs font-semibold"
                            />
                            <Button
                              variant="ghost"
                              size="icon-sm"
                              disabled={savingSpeaker}
                              onClick={() => void saveSpeaker()}
                              title="Save speaker name"
                            >
                              <Check className="size-3.5" />
                            </Button>
                          </>
                        ) : (
                          <>
                            <span className="text-xs font-semibold text-amber-700 dark:text-amber-300">
                              {speakerName(segment.speaker)}
                            </span>
                            {onSpeakerSettingsChange && (
                              <button
                                type="button"
                                onClick={() =>
                                  startEditingSpeaker(segment.speaker, index)
                                }
                                className="opacity-0 text-stone-400 transition-opacity hover:text-stone-700 group-hover:opacity-100 focus:opacity-100 dark:hover:text-stone-200"
                                title={`Rename ${speakerName(segment.speaker)}`}
                              >
                                <Pencil className="size-3" />
                              </button>
                            )}
                          </>
                        )}
                      </div>
                      <button
                        type="button"
                        onClick={() => seek(segment.start)}
                        className="w-full text-left text-[15px] leading-6 text-stone-700 dark:text-stone-200"
                      >
                        <HighlightedText text={segment.text} query={query} />
                      </button>
                    </div>
                  </div>
                )
              })}
            </div>
          ) : transcription?.trim() ? (
            <div className="mx-auto max-w-3xl">
              <div className="mb-4 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-xs leading-5 text-amber-900 dark:border-amber-400/20 dark:bg-amber-400/10 dark:text-amber-200">
                This is a legacy plain-text transcript. Reprocess the recording to add
                speaker labels and synchronized timestamps.
              </div>
              <p className="whitespace-pre-wrap text-[15px] leading-7 text-stone-700 dark:text-stone-200">
                {transcription}
              </p>
            </div>
          ) : (
            <div className="flex h-full items-center justify-center">
              <div className="max-w-sm text-center">
                <Users className="mx-auto size-8 text-stone-300 dark:text-stone-600" />
                <p className="mt-3 text-sm font-medium">No transcript available</p>
                <p className="mt-1 text-xs leading-5 text-stone-500">
                  Process this recording to generate a speaker-timed transcript.
                </p>
              </div>
            </div>
          )}
        </div>
      </section>
    </div>
  )
}
