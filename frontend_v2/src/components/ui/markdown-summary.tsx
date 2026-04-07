import ReactMarkdown, { defaultUrlTransform } from "react-markdown"
import type { Components } from "react-markdown"
import remarkGfm from "remark-gfm"

interface MarkdownSummaryProps {
  content: string
  onOpenFile?: (filename: string) => void
}

/**
 * Renders markdown summaries with evidence:// link interception.
 * evidence:// links resolve to file lookups and open the document viewer.
 */
export function MarkdownSummary({ content, onOpenFile }: MarkdownSummaryProps) {
  const markdownUrlTransform = (url: string) => {
    if (url.startsWith("evidence://")) return url
    return defaultUrlTransform(url)
  }

  const components: Components = {
    a: ({ href, children }) => {
      if (href?.startsWith("evidence://")) {
        const rawFilename = href.replace("evidence://", "")
        let filename = rawFilename

        try {
          filename = decodeURIComponent(rawFilename)
        } catch {
          filename = rawFilename
        }

        return (
          <button
            type="button"
            className="text-amber-500 hover:text-amber-400 underline underline-offset-2 cursor-pointer"
            onClick={() => onOpenFile?.(filename)}
          >
            {children}
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
      <h2 className="text-sm font-semibold text-foreground mt-4 mb-1.5" {...props}>
        {children}
      </h2>
    ),
    h1: ({ children, ...props }) => (
      <h1 className="text-base font-semibold text-foreground mt-4 mb-2" {...props}>
        {children}
      </h1>
    ),
    h3: ({ children, ...props }) => (
      <h3 className="text-xs font-semibold text-foreground mt-3 mb-1" {...props}>
        {children}
      </h3>
    ),
    p: ({ children, ...props }) => (
      <p className="text-xs text-muted-foreground leading-relaxed mb-2" {...props}>
        {children}
      </p>
    ),
    ul: ({ children, ...props }) => (
      <ul className="text-xs text-muted-foreground list-disc pl-4 mb-2 space-y-0.5" {...props}>
        {children}
      </ul>
    ),
    ol: ({ children, ...props }) => (
      <ol className="text-xs text-muted-foreground list-decimal pl-4 mb-2 space-y-0.5" {...props}>
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
      <blockquote className="border-l-2 border-amber-500/30 pl-3 my-2 text-xs italic text-muted-foreground" {...props}>
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
