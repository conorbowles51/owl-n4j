import { lazy, Suspense, useState } from "react"
import type { GuideSource } from "@/components/ui/guide-dialog"
import { GLOSSARY_GUIDE, termAnchor } from "@/components/ui/glossary"

// the guide reader (markdown) loads only when a person asks for it, so a Learn more link costs the screen nothing
const GuideDialog = lazy(() => import("@/components/ui/guide-dialog").then((m) => ({ default: m.GuideDialog })))

/**
 * "Learn more" beside a term of art (lx-guidecover B): opens the glossary at that term, or a guide at one of its
 * sections. `term` is the glossary heading's words, e.g. "Set aside".
 */
export function LearnMore({
  term,
  guide = GLOSSARY_GUIDE,
  label = "Learn more",
  className = "",
}: {
  term: string
  guide?: GuideSource
  label?: string
  className?: string
}) {
  const [open, setOpen] = useState(false)
  return (
    <>
      <button
        type="button"
        className={`ml-1 inline text-[11px] text-primary underline underline-offset-2 hover:text-primary/80 ${className}`}
        aria-label={`${label}: ${term}`}
        data-glossary-term={guide.id === GLOSSARY_GUIDE.id ? term : undefined}
        onClick={() => setOpen(true)}
      >
        {label}
      </button>
      {open && (
        <Suspense fallback={null}>
          <GuideDialog guides={[guide]} anchor={termAnchor(term)} defaultOpen noTrigger onOpenChange={(o) => !o && setOpen(false)} />
        </Suspense>
      )}
    </>
  )
}
