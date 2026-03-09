import { fetchAPI } from "@/lib/api-client"
import type { ProcessingProfile, ProfileDetail, ProfileSaveData } from "@/types/evidence.types"

export const profilesAPI = {
  list: () => fetchAPI<ProcessingProfile[]>("/api/profiles"),

  get: (name: string) =>
    fetchAPI<ProfileDetail>(`/api/profiles/${encodeURIComponent(name)}`),

  save: (data: ProfileSaveData) =>
    fetchAPI<ProfileDetail>("/api/profiles", {
      method: "POST",
      body: data,
    }),

  delete: (name: string) =>
    fetchAPI<void>(`/api/profiles/${encodeURIComponent(name)}`, {
      method: "DELETE",
    }),
}
