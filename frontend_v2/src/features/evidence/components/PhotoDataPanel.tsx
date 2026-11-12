import { useEffect, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { fetchAPI } from "@/lib/api-client"
import { Button } from "@/components/ui/button"

type PhotoDetail = {
  read: boolean
  data: {
    width?: number
    height?: number
    date_taken?: { local: string; offset: string | null; field?: string }
    gps?: { latitude: number; longitude: number; altitude_m?: number }
    camera?: { make?: string; model?: string }
    read_by?: string
  }
  absent: string[]
  caption: string | null
  label: string | null
  time_words: string | null
}

/** What a photo's own data says, worded as unchecked, with the optional one-line caption. */
export function PhotoDataPanel({ caseId, fileId, canEdit }: { caseId: string; fileId: string; canEdit: boolean }) {
  const client = useQueryClient()
  const key = ["photo-data", caseId, fileId]
  const query = useQuery({
    queryKey: key,
    queryFn: () => fetchAPI<PhotoDetail>(`/api/photos/${fileId}?${new URLSearchParams({ case_id: caseId })}`),
  })
  const [caption, setCaption] = useState("")
  useEffect(() => setCaption(query.data?.caption ?? ""), [query.data?.caption])
  const save = useMutation({
    mutationFn: () =>
      fetchAPI(`/api/photos/${fileId}/caption?${new URLSearchParams({ case_id: caseId })}`, {
        method: "PUT",
        body: { caption },
      }),
    onSuccess: () => client.invalidateQueries({ queryKey: key }),
  })
  if (query.isLoading) return null
  if (query.error) return <p role="alert" className="text-xs text-destructive">Photo data could not be loaded.</p>
  const detail = query.data!
  const { data } = detail
  return (
    <div className="space-y-2 rounded-lg border p-3 text-xs" data-photo-data="">
      <p className="font-medium">Photo data</p>
      {!detail.read ? (
        <p className="text-muted-foreground">This photo’s own data has not been read yet. Process the file to read it.</p>
      ) : (
        <>
          <p className="text-muted-foreground">{detail.label}</p>
          <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1">
            <dt>Date taken</dt>
            <dd>{data.date_taken ? `${data.date_taken.local.slice(0, 10)} ${detail.time_words}` : "Not in the photo’s data"}</dd>
            <dt>Place</dt>
            <dd>
              {data.gps
                ? `${data.gps.latitude.toFixed(5)}, ${data.gps.longitude.toFixed(5)}${data.gps.altitude_m != null ? `, altitude ${data.gps.altitude_m} m` : ""}`
                : "Not in the photo’s data"}
            </dd>
            <dt>Camera</dt>
            <dd>{data.camera ? [data.camera.make, data.camera.model].filter(Boolean).join(" ") : "Not in the photo’s data"}</dd>
            {data.width && data.height ? (<><dt>Size</dt><dd>{data.width} × {data.height}</dd></>) : null}
          </dl>
          {detail.absent.length > 0 && <p>Absent from the file: {detail.absent.join(", ")}.</p>}
          {data.date_taken && <p className="text-muted-foreground">A camera’s clock can be wrong.</p>}
        </>
      )}
      <label className="grid gap-1">
        Caption (optional)
        <input
          type="text"
          maxLength={200}
          className="rounded border bg-background p-1.5"
          value={caption}
          disabled={!canEdit || save.isPending}
          onChange={(e) => setCaption(e.target.value)}
        />
      </label>
      {canEdit && caption !== (detail.caption ?? "") && (
        <Button size="sm" variant="outline" disabled={save.isPending} onClick={() => save.mutate()}>
          {save.isPending ? "Saving…" : "Save caption"}
        </Button>
      )}
      {save.error && <p role="alert" className="text-destructive">{(save.error as Error).message}</p>}
    </div>
  )
}
