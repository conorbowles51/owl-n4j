import { lazy, Suspense } from "react"
import type { LookIntoProps } from "./LookIntoButton"

// The button and its dialog load when a screen that offers it opens, not with the shell (the main script has a size limit).
const Button = lazy(() => import("./LookIntoButton").then((m) => ({ default: m.LookIntoButton })))

export function LookInto(props: LookIntoProps) {
  return <Suspense fallback={null}><Button {...props} /></Suspense>
}
