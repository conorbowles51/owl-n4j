import ReactMarkdown, { defaultUrlTransform } from "react-markdown"
import remarkGfm from "remark-gfm"
import type { Components } from "react-markdown"

function parseDocumentHref(href: string | undefined) {
  if (!href?.startsWith("doc://")) return null

  const rawTarget = href.slice("doc://".length)
  const lastSlash = rawTarget.lastIndexOf("/")
  const rawFilename = lastSlash >= 0 ? rawTarget.slice(0, lastSlash) : rawTarget
  const rawPage = lastSlash >= 0 ? rawTarget.slice(lastSlash + 1) : ""

  let filename = rawFilename
  try {
    filename = decodeURIComponent(rawFilename)
  } catch {
    filename = rawFilename
  }

  const page = Number.parseInt(rawPage, 10)
  return {
    filename,
    page: Number.isFinite(page) ? page : undefined,
  }
}

interface MarkdownProps {
  content: string
  className?: string
  onOpenDocument?: (filename: string, page?: number) => void
}

export function Markdown({
  content,
  className,
  onOpenDocument,
}: MarkdownProps) {
  const markdownUrlTransform = (url: string) => {
    if (url.startsWith("doc://")) return url
    return defaultUrlTransform(url)
  }

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
      const documentTarget = parseDocumentHref(href)
      if (documentTarget && onOpenDocument) {
        return (
          <button
            type="button"
            className="text-blue-500 underline hover:text-blue-600"
            onClick={() =>
              onOpenDocument(documentTarget.filename, documentTarget.page)
            }
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
    <div className={className}>
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
