import { useQuery, useMutation } from "@tanstack/react-query"
import { evidenceAPI } from "../api"

export function useFolderFiles(caseId: string, folderPath: string, enabled = true) {
  return useQuery({
    queryKey: ["folder-files", caseId, folderPath],
    queryFn: async () => {
      const res = await evidenceAPI.listFolderFiles(caseId, folderPath)
      return res.files
    },
    enabled: enabled && !!caseId && !!folderPath,
  })
}

export function useGenerateFolderProfile() {
  return useMutation({
    mutationFn: (request: {
      case_id: string
      folder_path: string
      instructions: string
      profile_name?: string
    }) => evidenceAPI.generateFolderProfile(request),
  })
}

export function useTestFolderProfile() {
  return useMutation({
    mutationFn: (request: {
      case_id: string
      folder_path: string
      profile_config: Record<string, unknown>
    }) => evidenceAPI.testFolderProfile(request),
  })
}
