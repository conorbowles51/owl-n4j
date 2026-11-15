import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { fetchAPI } from "@/lib/api-client"
import { type UncheckedClaims, uncheckedClaimsText } from "../utils/unchecked-claims"

/** How many of this file's claims are unchecked, with the request to check the case's unchecked claims. */
export function UncheckedClaimsNotice({ fileId, caseId }: { fileId: string; caseId: string }) {
  const queryClient = useQueryClient()
  const counts = useQuery({
    queryKey: ["claim-checks", caseId],
    queryFn: ({ signal }) => fetchAPI<UncheckedClaims>(`/api/claim-checks/${caseId}`, { signal }),
    staleTime: 60_000,
  })
  const check = useMutation({
    mutationFn: () =>
      fetchAPI<{ queued: boolean; message: string }>(`/api/claim-checks/${caseId}/check`, { method: "POST" }),
    onSuccess: (answer) => {
      toast.success(answer.message)
      void queryClient.invalidateQueries({ queryKey: ["claim-checks", caseId] })
    },
    onError: (error: Error) => toast.error(error.message),
  })
  const count = counts.data?.files.find((f) => f.evidence_file_id === fileId)?.unchecked ?? 0
  if (!count) return null
  const total = counts.data?.unchecked ?? count
  return (
    <div role="status" className="mb-2 space-y-1 rounded border border-amber-500/40 bg-amber-500/10 p-2 text-xs">
      <p>{uncheckedClaimsText(count)}</p>
      <p>
        Checking reads each claim against its file and spends from the case&apos;s AI budget.
        {total > count ? ` The case has ${total.toLocaleString()} unchecked claims in all; the check takes them all, smallest file first.` : ""}
      </p>
      <Button size="sm" variant="outline" disabled={check.isPending} onClick={() => check.mutate()}>
        Check them
      </Button>
    </div>
  )
}
