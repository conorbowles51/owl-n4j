import { Suspense, type ReactNode } from "react"
import { ErrorBoundary } from "@/components/ui/error-boundary"
import { LoadingWords } from "@/components/ui/loading-spinner"

/**
 * A panel whose code loads on first show (lazy import): while it arrives the panel says so in words, and a failed
 * download (a release replaced the files, the network dropped) shows the error and a retry inside the panel, never a
 * blank panel or a broken page around it.
 */
export function LazyPanel({ children, words = "Opening the panel…" }: { children: ReactNode; words?: string }) {
  return (
    <ErrorBoundary level="section">
      <Suspense fallback={<LoadingWords className="p-4">{words}</LoadingWords>}>{children}</Suspense>
    </ErrorBoundary>
  )
}
