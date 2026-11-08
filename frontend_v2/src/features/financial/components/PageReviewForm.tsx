import { useEffect, useState } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { Button } from "@/components/ui/button"
import { fetchAPI } from "@/lib/api-client"
import {
  pageReviewKey,
  pageReviewUrl,
  parsePageReviews,
  type usePageReviews,
} from "../hooks/use-page-reviews"

const answers = [
  ["supporting_correspondence", "Supporting correspondence"],
  ["continuation", "Continuation of a statement"],
  ["blank", "Blank page"],
  ["other", "Other"],
] as const

function ReviewAuthor({
  saved_by,
  saved_at,
  origin,
  canEdit,
}: {
  saved_by: string | null
  saved_at: string
  origin: Record<string, unknown> | null
  canEdit?: boolean
}) {
  return (
    <>
      {origin
        ? `Read by ${String(origin.model || "a model")} · not confirmed`
        : `Saved by ${saved_by || "someone not recorded"}`}{" "}
      on {new Date(saved_at).toLocaleString()}
      {origin &&
        (canEdit
          ? ". Check the page, then save your own review below to confirm or replace it; this one stays in the history."
          : ". An editor of this case can confirm this.")}
    </>
  )
}

/** What a person found on this page. It clears no coverage check and adds no payment. */
export function PageReviewForm({
  caseId,
  fileId,
  page,
  reviews,
  canEdit,
}: {
  caseId: string
  fileId: string
  page: number
  reviews: ReturnType<typeof usePageReviews>
  canEdit: boolean
}) {
  const client = useQueryClient()
  const current = reviews.byPage.get(page)
  const [disposition, setDisposition] = useState("")
  const [reason, setReason] = useState("")
  useEffect(() => {
    setDisposition("")
    setReason("")
  }, [page, current?.id])
  const store = (value: unknown) =>
    client.setQueryData(pageReviewKey(caseId, fileId), parsePageReviews(value))
  const save = useMutation({
    retry: false,
    mutationFn: () =>
      fetchAPI(pageReviewUrl(fileId, caseId, `/${page}`), {
        method: "PUT",
        body: {
          disposition,
          reason,
          expected_review_id: current?.id ?? null,
        },
      }),
    onSuccess: store,
    onError: () =>
      void client.invalidateQueries({
        queryKey: pageReviewKey(caseId, fileId),
      }),
  })
  const undo = useMutation({
    retry: false,
    mutationFn: () =>
      fetchAPI(pageReviewUrl(fileId, caseId, `/${page}/undo`), {
        method: "POST",
        body: { expected_review_id: current?.id ?? null },
      }),
    onSuccess: store,
  })
  const earlier = reviews.history.filter(
    (item) => item.page_number === page && item.id !== current?.id
  )
  const busy = save.isPending || undo.isPending
  return (
    <section
      className="rounded border p-3 mt-3 space-y-2"
      aria-label={`Review of page ${page}`}
    >
      <h4 className="font-medium">Review of page {page}</h4>
      {reviews.failed && (
        <p role="alert">Saved page reviews could not be loaded.</p>
      )}
      {current ? (
        <div className="space-y-1">
          <p>
            {current.label}: {current.reason}
          </p>
          <p className="text-muted-foreground">
            <ReviewAuthor {...current} canEdit={canEdit} />
          </p>
          {!current.same_file_bytes && (
            <p>This review was saved against a different copy of the file.</p>
          )}
          {canEdit && (
            <Button
              variant="outline"
              size="sm"
              disabled={busy}
              onClick={() => undo.mutate()}
            >
              Undo this review
            </Button>
          )}
        </div>
      ) : (
        <p className="text-muted-foreground">No saved review of this page.</p>
      )}
      <p className="text-muted-foreground">
        A review records what the page is. It adds no payment and does not
        confirm coverage of any dates.
      </p>
      {canEdit && (
        <fieldset disabled={busy} className="space-y-2">
          <label className="block">
            This page is
            <select
              aria-label={`What page ${page} is`}
              className="block w-full rounded border bg-background p-2"
              value={disposition}
              onChange={(event) => setDisposition(event.target.value)}
            >
              <option value="">Choose…</option>
              {answers.map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <label className="block">
            Why, from what the page shows
            <textarea
              aria-label={`Why, for page ${page}`}
              className="block w-full rounded border bg-background p-2"
              maxLength={2000}
              value={reason}
              onChange={(event) => setReason(event.target.value)}
            />
          </label>
          <Button
            variant="outline"
            disabled={!disposition || !reason.trim()}
            onClick={() => save.mutate()}
          >
            {save.isPending ? "Saving…" : `Save review of page ${page}`}
          </Button>
        </fieldset>
      )}
      {(save.isError || undo.isError) && (
        <p role="alert">{(save.error ?? undo.error)?.message}</p>
      )}
      {earlier.length > 0 && (
        <ul className="text-muted-foreground">
          {earlier.map((item) => (
            <li key={item.id}>
              Earlier: {item.label}: {item.reason} (
              <ReviewAuthor {...item} canEdit={canEdit} />
              {item.undone_at
                ? `; undone by ${item.undone_by || "someone not recorded"}`
                : ""}
              )
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
