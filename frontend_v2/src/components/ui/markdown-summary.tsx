import ReactMarkdown from "react-markdown"
import type { Components } from "react-markdown"

interface MarkdownSummaryProps {
  content: string
  onOpenFile?: (filename: string) => void
}

/**
 * Renders markdown summaries with evidence:// link interception.
 * evidence:// links resolve to file lookups and open the document viewer.
 */
export function MarkdownSummary({ content, onOpenFile }: MarkdownSummaryProps) {
  const components: Components = {
    a: ({ href, children, ...props }) => {
      if (href?.startsWith("evidence://")) {
        const filename = href.replace("evidence://", "")
        return (
          <button
            type="button"
            className="text-amber-500 hover:text-amber-400 underline underline-offset-2 cursor-pointer"
            onClick={() => onOpenFile?.(filename)}
            {...props}
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
          {...props}
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
  }

  return (
    <div className="prose-evidence">
      <ReactMarkdown components={components}>{content}</ReactMarkdown>
    </div>
  )
}
