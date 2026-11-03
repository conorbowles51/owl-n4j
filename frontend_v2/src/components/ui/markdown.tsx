import ReactMarkdown, { defaultUrlTransform } from "react-markdown"
import remarkGfm from "remark-gfm"
import type { Components } from "react-markdown"
import { appPath, parseCitation } from "@/lib/citations"
import { CitationLink, CitationScope, WithCitations } from "@/components/citations/citations"

interface MarkdownProps {
  content: string
  className?: string
}

/** Markdown with citations (doc://, txn://, rec://, and the older forms) checked against the case and opened by the
 * enclosing CitationProvider (one is made from the route's case when none encloses it). */
export function Markdown({ content, className }: MarkdownProps) {
  const markdownUrlTransform = (url: string) => (parseCitation(url) ? url : defaultUrlTransform(appPath(url) ?? url))

  const components: Components = {
    h1: ({ children }) => (
      <h1 className="mt-4 mb-2 text-lg font-bold text-foreground">{children}</h1>
    ),
    h2: ({ children }) => (
      <h2 className="mt-3 mb-1.5 text-base font-semibold text-foreground">{children}</h2>
    ),
    h3: ({ children }) => (
      <h3 className="mt-2 mb-1 text-sm font-semibold text-foreground">{children}</h3>
    ),
    p: ({ children }) => (
      <p className="mb-2 last:mb-0">{children}</p>
    ),
    ul: ({ children }) => (
      <ul className="mb-2 ml-4 list-disc space-y-0.5">{children}</ul>
    ),
    ol: ({ children }) => (
      <ol className="mb-2 ml-4 list-decimal space-y-0.5">{children}</ol>
    ),
    li: ({ children }) => <li>{children}</li>,
    strong: ({ children }) => (
      <strong className="font-semibold">{children}</strong>
    ),
    a: ({ href, children }) => {
      const citation = parseCitation(href)
      if (citation) return <CitationLink citation={citation}>{children}</CitationLink>
      // a Loupe page the model wrote with an invented host opens the page itself
      return (
        <a
          href={appPath(href) ?? href}
          target="_blank"
          rel="noopener noreferrer"
          className="text-blue-500 underline hover:text-blue-600"
        >
          {children}
        </a>
      )
    },
    blockquote: ({ children }) => (
      <blockquote className="my-2 border-l-2 border-muted-foreground/30 pl-3 italic text-muted-foreground">
        {children}
      </blockquote>
    ),
    code: ({ className, children }) => {
      const isBlock = className?.includes("language-")
      if (isBlock) {
        return (
          <pre className="my-2 overflow-x-auto rounded-md bg-muted p-3 text-xs">
            <code>{children}</code>
          </pre>
        )
      }
      return (
        <code className="rounded bg-muted px-1 py-0.5 text-xs">{children}</code>
      )
    },
    pre: ({ children }) => <>{children}</>,
    table: ({ children }) => (
      <div className="my-2 overflow-x-auto">
        <table className="w-full border-collapse text-xs">{children}</table>
      </div>
    ),
    th: ({ children }) => (
      <th className="border border-border bg-muted px-2 py-1 text-left font-semibold">
        {children}
      </th>
    ),
    td: ({ children }) => (
      <td className="border border-border px-2 py-1">{children}</td>
    ),
  }

  return (
    <WithCitations>
      <CitationScope content={content}>
        <div className={className}>
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            components={components}
            urlTransform={markdownUrlTransform}
          >
            {content}
          </ReactMarkdown>
        </div>
      </CitationScope>
    </WithCitations>
  )
}
