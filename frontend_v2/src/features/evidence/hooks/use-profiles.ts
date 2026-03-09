import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { profilesAPI } from "../profiles.api"
import type { ProfileSaveData } from "@/types/evidence.types"

export function useProfiles() {
  return useQuery({
    queryKey: ["profiles"],
    queryFn: () => profilesAPI.list(),
  })
}

export function useProfile(name: string | undefined) {
  return useQuery({
    queryKey: ["profile", name],
    queryFn: () => profilesAPI.get(name!),
    enabled: !!name,
  })
}

export function useSaveProfile() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (data: ProfileSaveData) => profilesAPI.save(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["profiles"] })
    },
  })
}

export function useDeleteProfile() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (name: string) => profilesAPI.delete(name),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["profiles"] })
    },
  })
}
