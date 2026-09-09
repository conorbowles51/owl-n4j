import type { SummarySource } from "@/lib/summary-sources"

export function SummarySources({
  sources,
  onOpenFile,
}: {
  sources: SummarySource[]
  onOpenFile: (filename: string, page?: number) => void
}) {
  return (
    <section className="min-w-0 px-4 py-3" aria-label="Summary sources">
      <h4 className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
        Summary sources
      </h4>
      <ol className="space-y-2">
        {sources.map((source) => (
          <li
            key={source.filename}
            className="flex min-w-0 items-start gap-2 text-xs"
          >
            <span className="mt-1 shrink-0 font-semibold tabular-nums text-muted-foreground">
              S{source.number}
            </span>
            <div className="min-w-0 flex-1">
              <button
                type="button"
                className="w-full rounded-sm py-1 text-left text-foreground [overflow-wrap:anywhere] hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-500"
                onClick={() => onOpenFile(source.filename)}
                aria-label={`Open source S${source.number}: ${source.filename}`}
              >
                {source.filename}
              </button>
              {source.pages.length > 0 && (
                <div className="flex flex-wrap gap-x-2 gap-y-1">
                  {source.pages.map((page) => (
                    <button
                      key={page}
                      type="button"
                      className="rounded-sm text-[11px] tabular-nums text-amber-600 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-500 dark:text-amber-400"
                      onClick={() => onOpenFile(source.filename, page)}
                      aria-label={`Open source S${source.number}, page ${page}`}
                    >
                      p.{page}
                    </button>
                  ))}
                </div>
              )}
            </div>
          </li>
        ))}
      </ol>
    </section>
  )
}
