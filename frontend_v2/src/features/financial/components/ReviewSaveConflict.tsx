import { useQuery } from "@tanstack/react-query"
import { Button } from "@/components/ui/button"
import { reviewDifferences, type SavedReview } from "../lib/review-conflict"

/** After a refused save: the review as saved beside this person's values, and their choice between them. */
export function ReviewSaveConflict({
  queryKey,
  read,
  local,
  busy,
  onKeepSaved,
  onReapply,
}: {
  queryKey: unknown[]
  read: () => Promise<SavedReview | null>
  local: Record<string, unknown>
  busy: boolean
  onKeepSaved: (saved: SavedReview) => void
  onReapply: (saved: SavedReview) => void
}) {
  const query = useQuery({
    queryKey,
    queryFn: read,
    retry: false,
    gcTime: 0,
    staleTime: 0,
  })
  const saved = query.data
  const differences = saved ? reviewDifferences(saved.request, local) : []
  return (
    <section
      role="alert"
      className="rounded border p-3 space-y-2 text-sm"
      aria-label="Saved review and your unsaved values"
    >
      <h4 className="font-medium">
        A newer review was saved while you were working
      </h4>
      <p>
        Nothing has been overwritten. Your values are still here. Compare them
        with the saved review, then choose which to keep.
      </p>
      {query.isPending && <p role="status">Loading the saved review…</p>}
      {query.isError && (
        <div className="space-y-2">
          <p>The saved review could not be loaded. {query.error.message}</p>
          <Button variant="outline" onClick={() => void query.refetch()}>
            Load the saved review again
          </Button>
        </div>
      )}
      {query.isSuccess && !saved && (
        <p>No saved review was found. Save progress again to keep your values.</p>
      )}
      {saved && (
        <>
          <p>
            Saved by {saved.saved_by?.name || "someone not recorded"}
            {saved.saved_at
              ? ` on ${new Date(saved.saved_at).toLocaleString()}`
              : ""}
            .
          </p>
          {differences.length ? (
            <div className="overflow-auto max-h-72">
              <table className="w-full text-left">
                <thead>
                  <tr>
                    <th scope="col">Field</th>
                    <th scope="col">Saved</th>
                    <th scope="col">Your unsaved value</th>
                  </tr>
                </thead>
                <tbody>
                  {differences.map((item) => (
                    <tr key={item.key} className="align-top border-t">
                      <th scope="row" className="font-normal pr-2 break-words">
                        {item.label}
                      </th>
                      <td className="pr-2 break-words">{item.saved}</td>
                      <td className="break-words">{item.local}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p>The saved review and your values show no differences.</p>
          )}
          <div className="flex flex-wrap gap-2">
            <Button
              variant="outline"
              disabled={busy}
              onClick={() => onKeepSaved(saved)}
            >
              Keep the saved review
            </Button>
            <Button disabled={busy} onClick={() => onReapply(saved)}>
              Save my values over it
            </Button>
          </div>
          <p className="text-muted-foreground">
            Keeping the saved review discards your unsaved values. Saving yours
            records the change against the saved review.
          </p>
        </>
      )}
    </section>
  )
}
