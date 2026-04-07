import { fetchAPI } from "@/lib/api-client"
import type { ProcessingProfile } from "@/types/evidence.types"

export type Profile = ProcessingProfile

export interface SetupStatus {
  needs_setup: boolean
}

export const profilesAPI = {
  list: () => fetchAPI<Profile[]>("/api/profiles"),

  get: (profileName: string) =>
    fetchAPI<Profile>(`/api/profiles/${encodeURIComponent(profileName)}`),

  save: (profileData: Profile) =>
    fetchAPI<Profile>("/api/profiles", {
      method: "POST",
      body: profileData,
    }),

  delete: (profileName: string) =>
    fetchAPI<void>(`/api/profiles/${encodeURIComponent(profileName)}`, {
      method: "DELETE",
    }),
}

export const setupAPI = {
  getStatus: () => fetchAPI<SetupStatus>("/api/setup/status"),

  createInitialUser: (data: {
    email: string
    name: string
    password: string
  }) =>
    fetchAPI<void>("/api/setup/initial-user", {
      method: "POST",
      body: data,
    }),
}
