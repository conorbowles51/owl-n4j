import ReactMarkdown, { defaultUrlTransform } from "react-markdown"
import type { Components } from "react-markdown"
import remarkGfm from "remark-gfm"
import { parseDocumentCitation } from "@/lib/summary-sources"

interface MarkdownSummaryProps {
  content: string
  sourceNumbers?: ReadonlyMap<string, number>
  onOpenFile?: (filename: string, page?: number) => void
}

/**
 * Renders markdown summaries with evidence:// link interception.
 * evidence:// links resolve to file lookups and open the document viewer.
 */
export function MarkdownSummary({
  content,
  onOpenFile,
  sourceNumbers,
}: MarkdownSummaryProps) {
  const markdownUrlTransform = (url: string) => {
    if (url.startsWith("evidence://") || url.startsWith("doc://")) return url
    return defaultUrlTransform(url)
  }

  const components: Components = {
    a: ({ href, children }) => {
      const citation = parseDocumentCitation(href)
      if (citation) {
        const sourceNumber = sourceNumbers?.get(citation.filename)
        const label =
          sourceNumber === undefined ? undefined : `S${sourceNumber}`
        const pageLabel =
          citation.page === undefined ? "" : `, p.${citation.page}`
        return (
          <button
            type="button"
            className={
              label
                ? "inline-flex cursor-pointer whitespace-nowrap rounded-sm px-0.5 text-[11px] font-medium tabular-nums text-amber-600 hover:bg-amber-500/10 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-500 dark:text-amber-400"
                : "cursor-pointer text-amber-500 underline underline-offset-2 hover:text-amber-400"
            }
            title={label ? `${citation.filename}${pageLabel}` : undefined}
            aria-label={
              label
                ? `Open source ${label}: ${citation.filename}${pageLabel}`
                : undefined
            }
            onClick={() => onOpenFile?.(citation.filename, citation.page)}
          >
            {label ? `[${label}${pageLabel}]` : children}
          </button>
        )
      }
      return (
        <a
          href={href}
          target="_blank"
          rel="noopener noreferrer"
          className="text-amber-500 hover:text-amber-400 underline underline-offset-2"
        >
          {children}
        </a>
      )
    },
    h2: ({ children, ...props }) => (
      <h2
        className="text-sm font-semibold text-foreground mt-4 mb-1.5"
        {...props}
      >
        {children}
      </h2>
    ),
    h1: ({ children, ...props }) => (
      <h1
        className="text-base font-semibold text-foreground mt-4 mb-2"
        {...props}
      >
        {children}
      </h1>
    ),
    h3: ({ children, ...props }) => (
      <h3
        className="text-xs font-semibold text-foreground mt-3 mb-1"
        {...props}
      >
        {children}
      </h3>
    ),
    p: ({ children, ...props }) => (
      <p
        className="text-xs text-muted-foreground leading-relaxed mb-2"
        {...props}
      >
        {children}
      </p>
    ),
    ul: ({ children, ...props }) => (
      <ul
        className="text-xs text-muted-foreground list-disc pl-4 mb-2 space-y-0.5"
        {...props}
      >
        {children}
      </ul>
    ),
    ol: ({ children, ...props }) => (
      <ol
        className="text-xs text-muted-foreground list-decimal pl-4 mb-2 space-y-0.5"
        {...props}
      >
        {children}
      </ol>
    ),
    li: ({ children, ...props }) => (
      <li className="leading-relaxed" {...props}>
        {children}
      </li>
    ),
    strong: ({ children, ...props }) => (
      <strong className="font-semibold text-foreground" {...props}>
        {children}
      </strong>
    ),
    blockquote: ({ children, ...props }) => (
      <blockquote
        className="border-l-2 border-amber-500/30 pl-3 my-2 text-xs italic text-muted-foreground"
        {...props}
      >
        {children}
      </blockquote>
    ),
    code: ({ className, children, ...props }) => {
      const isBlock = className?.includes("language-")
      if (isBlock) {
        return (
          <pre className="my-2 overflow-x-auto rounded-md bg-muted p-3 text-xs">
            <code {...props}>{children}</code>
          </pre>
        )
      }
      return (
        <code className="rounded bg-muted px-1 py-0.5 text-[11px]" {...props}>
          {children}
        </code>
      )
    },
    pre: ({ children }) => <>{children}</>,
  }

  return (
    <div className="prose-evidence">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={components}
        urlTransform={markdownUrlTransform}
      >
        {content}
      </ReactMarkdown>
    </div>
  )
}
