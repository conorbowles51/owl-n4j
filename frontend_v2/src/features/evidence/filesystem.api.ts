import { fetchAPI } from "@/lib/api-client"
import type { FilesystemItem } from "@/types/evidence.types"

export const filesystemAPI = {
  list: (caseId: string, path?: string) => {
    const qs = new URLSearchParams({ case_id: caseId })
    if (path) qs.set("path", path)
    return fetchAPI<{ items: FilesystemItem[] }>(`/api/filesystem/list?${qs}`)
  },

  readFile: (caseId: string, path: string) => {
    const qs = new URLSearchParams({ case_id: caseId, path })
    return fetchAPI<{ content: string }>(`/api/filesystem/read?${qs}`)
  },
}
