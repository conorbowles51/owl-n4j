import { useState } from "react"
import { Info } from "lucide-react"
import { LearnMore } from "@/components/ui/learn-more"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"

/**
 * The ⓘ that replaces an explanatory paragraph. Hover or keyboard focus shows the text as a tooltip; clicking (or
 * Enter) pins it open on the page, so the explanation is never hover-only. With `term`, the pinned text ends with "Learn more", which opens the
 * glossary at that term.
 */
export function InfoTip({ text, tone = "light", term }: { text: string; tone?: "light" | "dark"; term?: string }) {
  const [open, setOpen] = useState(false)
  return (
    <span className="inline">
      <Tooltip>
        <TooltipTrigger asChild>
          <button
            type="button"
            aria-label={open ? "Hide explanation" : `About this: ${text}`}
            aria-expanded={open}
            onClick={() => setOpen(!open)}
            className={`ml-1.5 inline-flex size-5 items-center justify-center rounded-full align-middle ${tone === "dark" ? "text-[#9a9da5] hover:text-white" : "text-muted-foreground hover:text-foreground"}`}
          >
            <Info aria-hidden="true" className="size-4" />
          </button>
        </TooltipTrigger>
        {!open && <TooltipContent className="max-w-xs">{text}</TooltipContent>}
      </Tooltip>
      {open && (
        <span
          role="note"
          className={`mt-1 block max-w-prose text-[13px] font-normal leading-snug tracking-normal ${tone === "dark" ? "text-[#bfc1c8]" : "text-muted-foreground"}`}
          style={{ fontFamily: "inherit" }}
        >
          {text}
          {term && <LearnMore term={term} />}
        </span>
      )}
    </span>
  )
}
