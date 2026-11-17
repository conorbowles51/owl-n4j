import { lazy, Suspense } from "react"
import type { ComponentProps } from "react"

// The overlay code loads when a screen shows it, not with the shell (the main script has a size limit).
const Panel = lazy(() => import("./TogetherPanel").then((m) => ({ default: m.TogetherPanel })))
const Layer = lazy(() => import("./MeetingLayer").then((m) => ({ default: m.MeetingLayer })))
const Band = lazy(() => import("./TogetherBand").then((m) => ({ default: m.TogetherBand })))

export const LazyTogetherPanel = (p: ComponentProps<typeof import("./TogetherPanel").TogetherPanel>) => <Suspense fallback={null}><Panel {...p} /></Suspense>
export const LazyMeetingLayer = (p: ComponentProps<typeof import("./MeetingLayer").MeetingLayer>) => <Suspense fallback={null}><Layer {...p} /></Suspense>
export const LazyTogetherBand = (p: ComponentProps<typeof import("./TogetherBand").TogetherBand>) => <Suspense fallback={null}><Band {...p} /></Suspense>
