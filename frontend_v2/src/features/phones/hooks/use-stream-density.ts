import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { getReaderSettings, saveReaderSettings, type StreamDensity } from "../api"

const KEY = ["phone-reader-settings"]

/** Comfortable or Compact (07 section 4.4), saved for the person on the server. The list shows the choice at once;
 * a save that fails says so and the list goes back to what is saved. */
export function useStreamDensity() {
  const qc = useQueryClient()
  const q = useQuery({ queryKey: KEY, queryFn: getReaderSettings, staleTime: 5 * 60_000, retry: false })
  const save = useMutation({
    mutationFn: saveReaderSettings,
    onMutate: (density: StreamDensity) => {
      const before = qc.getQueryData(KEY)
      qc.setQueryData(KEY, { stream_density: density })
      return { before }
    },
    onError: (_e, _d, ctx) => qc.setQueryData(KEY, ctx?.before),
  })
  return { density: q.data?.stream_density ?? ("comfortable" as StreamDensity), setDensity: save.mutate, saveFailed: save.isError }
}
