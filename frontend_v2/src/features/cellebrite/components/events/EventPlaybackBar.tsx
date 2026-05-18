import { useEffect, useMemo, useRef } from "react"
import { ChevronLeft, ChevronRight, Clock, Pause, Play, SkipBack, SkipForward } from "lucide-react"

import { Button } from "@/components/ui/button"
import { cn } from "@/lib/cn"

import type { TimelineItem } from "../../types"
import { dateRangeFromEvents, eventTimestamp, formatTs, parseTs, PLAYBACK_SPEEDS } from "./eventUtils"

export function EventPlaybackBar({
  events,
  playheadTime,
  isPlaying,
  playbackSpeed,
  onPlayheadChange,
  onPlayingChange,
  onPlaybackSpeedChange,
}: {
  events: TimelineItem[]
  playheadTime: Date | null
  isPlaying: boolean
  playbackSpeed: number
  onPlayheadChange: (date: Date) => void
  onPlayingChange: (playing: boolean) => void
  onPlaybackSpeedChange: (speed: number) => void
}) {
  const range = useMemo(() => dateRangeFromEvents(events), [events])
  const times = useMemo(
    () =>
      events
        .map((event) => parseTs(eventTimestamp(event))?.getTime())
        .filter((value): value is number => typeof value === "number")
        .sort((a, b) => a - b),
    [events]
  )
  const effectivePlayhead = playheadTime ?? range.min
  const rafRef = useRef<number | null>(null)
  const lastTickRef = useRef<number | null>(null)
  const pendingMsRef = useRef(0)

  useEffect(() => {
    if (!isPlaying || !range.min || !range.max) {
      if (rafRef.current) cancelAnimationFrame(rafRef.current)
      rafRef.current = null
      lastTickRef.current = null
      pendingMsRef.current = 0
      return
    }
    const min = range.min
    const max = range.max
    const commitMs = 100
    let sinceCommit = 0
    const tick = (now: number) => {
      if (lastTickRef.current == null) lastTickRef.current = now
      const delta = now - lastTickRef.current
      lastTickRef.current = now
      sinceCommit += delta
      pendingMsRef.current += delta * playbackSpeed
      if (sinceCommit >= commitMs) {
        const advance = pendingMsRef.current
        pendingMsRef.current = 0
        sinceCommit = 0
        const current = effectivePlayhead ?? min
        const nextMs = current.getTime() + advance
        if (nextMs >= max.getTime()) {
          onPlayheadChange(max)
          onPlayingChange(false)
        } else {
          onPlayheadChange(new Date(nextMs))
        }
      }
      rafRef.current = requestAnimationFrame(tick)
    }
    rafRef.current = requestAnimationFrame(tick)
    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current)
    }
  }, [effectivePlayhead, isPlaying, onPlaybackSpeedChange, onPlayheadChange, onPlayingChange, playbackSpeed, range.max, range.min])

  if (!range.min || !range.max) {
    return (
      <div className="flex h-11 shrink-0 items-center justify-center border-t border-border bg-card text-xs text-muted-foreground">
        No timestamped events to play back.
      </div>
    )
  }

  const totalMs = Math.max(1, range.max.getTime() - range.min.getTime())
  const fraction = effectivePlayhead
    ? Math.max(0, Math.min(1, (effectivePlayhead.getTime() - range.min.getTime()) / totalMs))
    : 0

  function scrub(clientX: number, left: number, width: number) {
    const ratio = Math.max(0, Math.min(1, (clientX - left) / Math.max(width, 1)))
    onPlayheadChange(new Date(range.min!.getTime() + ratio * totalMs))
  }

  function jumpPrevious() {
    if (!effectivePlayhead) return
    const current = effectivePlayhead.getTime()
    const target = [...times].reverse().find((time) => time < current - 1)
    if (target) onPlayheadChange(new Date(target))
  }

  function jumpNext() {
    if (!effectivePlayhead) return
    const current = effectivePlayhead.getTime()
    const target = times.find((time) => time > current + 1)
    if (target) onPlayheadChange(new Date(target))
  }

  return (
    <div className="flex h-12 shrink-0 items-center gap-2 border-t border-border bg-card px-3">
      <Button type="button" variant="ghost" size="icon-sm" onClick={() => onPlayheadChange(range.min!)}>
        <SkipBack className="size-4" />
      </Button>
      <Button type="button" variant="ghost" size="icon-sm" onClick={jumpPrevious}>
        <ChevronLeft className="size-4" />
      </Button>
      <Button
        type="button"
        variant="secondary"
        size="icon-sm"
        onClick={() => onPlayingChange(!isPlaying)}
      >
        {isPlaying ? <Pause className="size-4" /> : <Play className="size-4" />}
      </Button>
      <Button type="button" variant="ghost" size="icon-sm" onClick={jumpNext}>
        <ChevronRight className="size-4" />
      </Button>
      <Button type="button" variant="ghost" size="icon-sm" onClick={() => onPlayheadChange(range.max!)}>
        <SkipForward className="size-4" />
      </Button>
      <div
        className="relative h-2 flex-1 cursor-pointer rounded bg-muted"
        onClick={(event) => {
          const rect = event.currentTarget.getBoundingClientRect()
          scrub(event.clientX, rect.left, rect.width)
        }}
      >
        <div className="absolute inset-y-0 left-0 rounded bg-amber-500" style={{ width: `${fraction * 100}%` }} />
        <div className="absolute top-1/2 size-3 -translate-y-1/2 rounded-full border-2 border-card bg-amber-600 shadow" style={{ left: `calc(${fraction * 100}% - 6px)` }} />
      </div>
      <div className="hidden items-center gap-1 lg:flex">
        {PLAYBACK_SPEEDS.map((speed) => (
          <button
            key={speed}
            type="button"
            onClick={() => onPlaybackSpeedChange(speed)}
            className={cn(
              "rounded px-1.5 py-0.5 text-[10px]",
              playbackSpeed === speed ? "bg-amber-500 text-black" : "text-muted-foreground hover:bg-muted"
            )}
          >
            {speed}x
          </button>
        ))}
      </div>
      <div className="flex min-w-[170px] items-center gap-1 text-xs tabular-nums text-muted-foreground">
        <Clock className="size-3.5" />
        {formatTs(effectivePlayhead)}
      </div>
    </div>
  )
}
