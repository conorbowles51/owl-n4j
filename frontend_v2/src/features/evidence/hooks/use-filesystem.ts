import { useQuery } from "@tanstack/react-query"
import { filesystemAPI } from "../filesystem.api"

export function useFilesystemList(caseId: string | undefined, path?: string) {
  return useQuery({
    queryKey: ["filesystem", caseId, path],
    queryFn: async () => {
      const res = await filesystemAPI.list(caseId!, path)
      return res.items
    },
    enabled: !!caseId,
  })
}

export function useFileContent(caseId: string | undefined, path: string | undefined) {
  return useQuery({
    queryKey: ["file-content", caseId, path],
    queryFn: async () => {
      const res = await filesystemAPI.readFile(caseId!, path!)
      return res.content
    },
    enabled: !!caseId && !!path,
  })
}
