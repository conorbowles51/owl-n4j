import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { EyeOff } from "lucide-react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { ApiError } from "@/lib/api-client"
import { getSettings, putMediaBlur } from "@/features/phones/api"

const CHOICES: Array<{ value: "follow" | "on" | "off"; label: string }> = [
  { value: "follow", label: "Follow the kind of case (on in a criminal case)" },
  { value: "on", label: "Blur pictures for everyone by default" },
  { value: "off", label: "Do not blur pictures by default" },
]

/** The case default for blurring phone pictures in Media (03 8.3): on in a criminal case unless set here. Each
 * person can still turn blur off for themselves on the Media screen. */
export function MediaBlurSetting({ caseId }: { caseId: string }) {
  const qc = useQueryClient()
  const key = ["phone-settings", caseId]
  const q = useQuery({ queryKey: key, queryFn: () => getSettings(caseId), enabled: !!caseId })
  const [error, setError] = useState<string | null>(null)
  const change = useMutation({
    mutationFn: (v: boolean | null) => putMediaBlur(caseId, v),
    onSuccess: () => { setError(null); void qc.invalidateQueries({ queryKey: key }) },
    onError: (err) => setError(err instanceof ApiError && err.status === 403
      ? "You can view this case but not change it."
      : `Not changed: ${err instanceof Error ? err.message : "the server did not answer"}`),
  })
  const blur = q.data?.media_blur
  const current = !blur ? null : blur.set === null ? "follow" : blur.set ? "on" : "off"
  return (
    <Card className="mt-6 gap-4 p-5">
      <CardHeader className="grid-cols-[auto_1fr] grid-rows-[auto_auto] gap-x-3">
        <div className="row-span-2 flex size-9 items-center justify-center rounded-md border border-primary/20 bg-primary/10 text-primary">
          <EyeOff className="size-4" />
        </div>
        <CardTitle className="self-end text-base">Blur phone pictures</CardTitle>
        <CardDescription>Whether pictures from phones are blurred in Media until opened, by default for this case.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-2 text-sm">
        {q.isLoading && <p className="text-xs text-muted-foreground">Reading the setting…</p>}
        {q.isError && <p className="text-xs text-destructive">The setting could not be read. Nothing has changed.</p>}
        {blur && (
          <>
            <p>Now: {blur.default_on ? "blurred" : "not blurred"} by default. {blur.words}</p>
            <div role="radiogroup" aria-label="Blur phone pictures" className="space-y-1">
              {CHOICES.map((c) => (
                <label key={c.value} className="flex items-center gap-2">
                  <input type="radio" name="media-blur" checked={current === c.value} disabled={change.isPending}
                    onChange={() => change.mutate(c.value === "follow" ? null : c.value === "on")} />
                  {c.label}
                </label>
              ))}
            </div>
            <p className="text-xs text-muted-foreground">Each person can still turn blur off for themselves on the Media screen.</p>
          </>
        )}
        {error && <p role="alert" className="text-xs text-destructive">{error}</p>}
      </CardContent>
    </Card>
  )
}
