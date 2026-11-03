import type { SummarySource } from "@/lib/summary-sources"
import { docHref, docHrefByName, parseCitation } from "@/lib/citations"
import { CitationLink, CitationScope, WithCitations } from "@/components/citations/citations"

function sourceHref(source: SummarySource, page?: number) {
  return source.evidenceFileId ? docHref(source.evidenceFileId, page) : docHrefByName(source.filename, page)
}

/** The numbered sources of a summary. Each opens through the shared citation rules: a file by id, a name one file
 * of the case has, or a choice when several files share the name. */
export function SummarySources({ sources }: { sources: SummarySource[] }) {
  const hrefs = sources.flatMap((source) => [sourceHref(source), ...source.pages.map((page) => sourceHref(source, page))])
  return (
    <WithCitations>
      <CitationScope content={hrefs.map((href) => `[s](${href})`).join(" ")}>
        <section className="min-w-0 px-4 py-3" aria-label="Summary sources">
          <h4 className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            Summary sources
          </h4>
          <ol className="space-y-2">
            {sources.map((source) => (
              <li key={source.evidenceFileId ?? source.filename} className="flex min-w-0 items-start gap-2 text-xs">
                <span className="mt-1 shrink-0 font-semibold tabular-nums text-muted-foreground">S{source.number}</span>
                <div className="min-w-0 flex-1">
                  <CitationLink
                    citation={parseCitation(sourceHref(source))!}
                    className="w-full rounded-sm py-1 text-left text-foreground [overflow-wrap:anywhere] hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-500"
                    label={source.filename}
                    title={`S${source.number}`}
                  >
                    {source.filename}
                  </CitationLink>
                  {source.pages.length > 0 && (
                    <div className="flex flex-wrap gap-x-2 gap-y-1">
                      {source.pages.map((page) => (
                        <CitationLink
                          key={page}
                          citation={parseCitation(sourceHref(source, page))!}
                          className="rounded-sm text-[11px] tabular-nums text-amber-600 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-500 dark:text-amber-400"
                        >
                          p.{page}
                        </CitationLink>
                      ))}
                    </div>
                  )}
                </div>
              </li>
            ))}
          </ol>
        </section>
      </CitationScope>
    </WithCitations>
  )
}
