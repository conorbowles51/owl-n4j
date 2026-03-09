import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { snapshotsAPI, type SnapshotCreateData } from "../snapshots-api"

export function useSnapshots() {
  return useQuery({
    queryKey: ["snapshots"],
    queryFn: () => snapshotsAPI.list(),
  })
}

export function useSnapshot(snapshotId: string | undefined) {
  return useQuery({
    queryKey: ["snapshots", snapshotId],
    queryFn: () => snapshotsAPI.get(snapshotId!),
    enabled: !!snapshotId,
  })
}

export function useCreateSnapshot() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (data: SnapshotCreateData) => snapshotsAPI.create(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["snapshots"] })
    },
  })
}

export function useDeleteSnapshot() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (snapshotId: string) => snapshotsAPI.delete(snapshotId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["snapshots"] })
    },
  })
}
