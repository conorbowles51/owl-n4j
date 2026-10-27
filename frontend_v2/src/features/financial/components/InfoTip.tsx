import { useState } from "react"
import { Info } from "lucide-react"

/**
 * The ⓘ that replaces an explanatory paragraph. Hovering shows the text as a
 * title; clicking pins it open on the page, so the explanation is never
 * hover-only.
 */
export function InfoTip({ text, tone = "light" }: { text: string; tone?: "light" | "dark" }) {
  const [open, setOpen] = useState(false)
  return (
    <span className="inline">
      <button
        type="button"
        aria-label={open ? "Hide explanation" : `About this: ${text}`}
        aria-expanded={open}
        title={text}
        onClick={() => setOpen(!open)}
        className={`ml-1.5 inline-flex size-5 items-center justify-center rounded-full align-middle ${tone === "dark" ? "text-[#9a9da5] hover:text-white" : "text-muted-foreground hover:text-foreground"}`}
      >
        <Info aria-hidden="true" className="size-4" />
      </button>
      {open && (
        <span
          role="note"
          className={`mt-1 block max-w-prose text-[13px] font-normal leading-snug tracking-normal ${tone === "dark" ? "text-[#bfc1c8]" : "text-muted-foreground"}`}
          style={{ fontFamily: "inherit" }}
        >
          {text}
        </span>
      )}
    </span>
  )
}
