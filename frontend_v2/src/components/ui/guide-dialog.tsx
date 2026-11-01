import { useEffect, useState } from "react"
import { BookOpen } from "lucide-react"
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog"

/**
 * The generic Guide dialog (07 4.1, 9): FinancialGuide's dialog with its guides passed in, so the phone guide and
 * checklist open from a Guide button outside the scrolling content. The financial original stays where it is.
 */
export interface GuideSource {
  id: string
  /** Button label inside the dialog, e.g. "User guide". */
  label: string
  title: string
  url: string
  directory: string
  /** The document must start with this line (guards against an HTML fallback page). */
  heading: string
  prefix: string
}

const headingId = (prefix: string, text: string) =>
  `${prefix}-${text
    .toLowerCase()
    .replace(/[^a-z0-9\s-]/g, "")
    .trim()
    .replace(/\s+/g, "-")}`

export function GuideDialog({
  guides,
  trigger = "Guide",
  initial,
  defaultOpen = false,
  preloaded,
  anchor,
  onOpenChange,
}: {
  guides: GuideSource[]
  trigger?: string
  initial?: string
  defaultOpen?: boolean
  /** Documents already in hand (stories, tests); otherwise each is fetched when first shown. */
  preloaded?: Record<string, string>
  /** A heading to land on in the initial guide, e.g. a glossary term ("Learn more" links). */
  anchor?: string
  onOpenChange?: (open: boolean) => void
}) {
  const [open, setOpen] = useState(defaultOpen)
  const [active, setActive] = useState(initial ?? guides[0].id)
  const [documents, setDocuments] = useState<Record<string, string>>(preloaded ?? {})
  const [error, setError] = useState(false)
  const [attempt, setAttempt] = useState(0)
  const guide = guides.find((g) => g.id === active) ?? guides[0]
  const markdown = documents[guide.id]

  useEffect(() => {
    if (!open || markdown !== undefined) return
    const controller = new AbortController()
    void fetch(guide.url, { signal: controller.signal })
      .then(async (response) => {
        if (!response.ok) throw new Error("Guide unavailable")
        const text = await response.text()
        if (!text.startsWith(guide.heading)) throw new Error("Unexpected guide response")
        if (!controller.signal.aborted) setDocuments((previous) => ({ ...previous, [guide.id]: text }))
      })
      .catch(() => {
        if (!controller.signal.aborted) setError(true)
      })
    return () => controller.abort()
  }, [open, markdown, attempt, guide])

  const [landed, setLanded] = useState(false)
  useEffect(() => {
    if (!open || !anchor || landed || markdown === undefined || guide.id !== (initial ?? guides[0].id)) return
    const frame = requestAnimationFrame(() => {
      const target = document.getElementById(`${guide.prefix}-${anchor}`)
      if (target) {
        target.scrollIntoView({ block: "start" })
        target.setAttribute("tabindex", "-1")
        target.focus({ preventScroll: true })
      }
      setLanded(true)
    })
    return () => cancelAnimationFrame(frame)
  }, [open, anchor, landed, markdown, guide, initial, guides])

  return (
    <Dialog
      open={open}
      onOpenChange={(value) => {
        setOpen(value)
        setError(false)
        onOpenChange?.(value)
      }}
    >
      <DialogTrigger asChild>
        <Button variant="outline" size="sm">
          <BookOpen className="size-4" aria-hidden="true" />
          {trigger}
        </Button>
      </DialogTrigger>
      <DialogContent className="flex h-[92dvh] w-[96vw] max-w-none flex-col overflow-hidden p-4 sm:max-w-6xl sm:p-6">
        <DialogHeader className="shrink-0 pr-8 text-left">
          <DialogTitle>{guide.title}</DialogTitle>
          <DialogDescription>Step-by-step instructions. Close this guide to return to your case.</DialogDescription>
        </DialogHeader>
        {guides.length > 1 && (
          <div role="group" aria-label="Choose a guide" className="flex shrink-0 flex-wrap gap-2">
            {guides.map((g) => (
              <Button
                key={g.id}
                variant={active === g.id ? "secondary" : "outline"}
                size="sm"
                aria-pressed={active === g.id}
                onClick={() => {
                  setActive(g.id)
                  setError(false)
                }}
              >
                {g.label}
              </Button>
            ))}
          </div>
        )}
        <div
          key={guide.id}
          className="min-h-0 flex-1 overflow-auto rounded border bg-white p-4 text-slate-900 sm:p-8"
          tabIndex={0}
          role="region"
          aria-label={`${guide.title} contents`}
        >
          {error ? (
            <div role="alert">
              <p>The guide could not be loaded. Your case has not changed.</p>
              <Button
                variant="outline"
                className="mt-3"
                onClick={() => {
                  setError(false)
                  setAttempt((value) => value + 1)
                }}
              >
                Retry loading guide
              </Button>
            </div>
          ) : markdown === undefined ? (
            <p role="status">Loading the guide...</p>
          ) : (
            <article className="mx-auto max-w-4xl break-words text-base leading-7 [&_h1]:mb-5 [&_h1]:text-3xl [&_h1]:font-bold [&_h2]:mb-4 [&_h2]:mt-12 [&_h2]:border-t [&_h2]:pt-6 [&_h2]:text-2xl [&_h2]:font-bold [&_h3]:mb-3 [&_h3]:mt-8 [&_h3]:text-xl [&_h3]:font-semibold [&_p]:my-4 [&_ol]:list-decimal [&_ol]:pl-7 [&_ul]:list-disc [&_ul]:pl-7 [&_li]:my-2 [&_a]:text-rose-800 [&_a]:underline [&_img]:my-5 [&_img]:w-full [&_img]:rounded [&_img]:border [&_code]:rounded [&_code]:bg-slate-100 [&_code]:px-1 [&_table]:w-full [&_table]:border-collapse [&_th]:border [&_th]:bg-slate-100 [&_th]:p-3 [&_th]:text-left [&_td]:border [&_td]:p-3 [&_td]:align-top">
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                components={{
                  h2: ({ children }) => (
                    <h2 id={headingId(guide.prefix, String(children))}>
                      {children}
                    </h2>
                  ),
                  a: ({ href, children }) => (
                    <a
                      target={
                        href && !href.startsWith("#") ? "_blank" : undefined
                      }
                      rel={
                        href && !href.startsWith("#")
                          ? "noopener noreferrer"
                          : undefined
                      }
                      href={
                        href?.startsWith("#")
                          ? `#${guide.prefix}-${href.slice(1)}`
                          : href &&
                              !href.startsWith("/") &&
                              !/^[a-z][a-z0-9+.-]*:/i.test(href)
                            ? `${guide.directory}${href}`
                            : href
                      }
                      onClick={(event) => {
                        if (href?.startsWith("#")) {
                          event.preventDefault()
                          document
                            .getElementById(`${guide.prefix}-${href.slice(1)}`)
                            ?.scrollIntoView({ block: "start" })
                        }
                      }}
                    >
                      {children}
                    </a>
                  ),
                  img: ({ src, alt }) => (
                    <img
                      src={
                        src?.startsWith("images/")
                          ? `${guide.directory}${src}`
                          : undefined
                      }
                      alt={alt}
                      loading="lazy"
                    />
                  ),
                  table: ({ children }) => (
                    <div className="my-5 overflow-x-auto">
                      <table>{children}</table>
                    </div>
                  ),
                }}
              >
                {markdown}
              </ReactMarkdown>
            </article>
          )}
        </div>
      </DialogContent>
    </Dialog>
  )
}
