import { lazy, Suspense } from "react"

const Inner = lazy(() => import("./RelationTray").then((m) => ({ default: m.RelationTray })))

/** The look in progress; its code loads after the shell, so the main script stays small. */
export function Tray() {
  return <Suspense fallback={null}><Inner /></Suspense>
}
