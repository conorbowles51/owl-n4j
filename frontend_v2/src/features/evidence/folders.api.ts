import { fetchAPI } from "@/lib/api-client"
import type {
  FolderTreeNode,
  FolderContentsResponse,
  FolderProfile,
  EffectiveProfile,
} from "@/types/evidence.types"

export const foldersAPI = {
  getTree: async (caseId: string) => {
    const res = await fetchAPI<{ tree: FolderTreeNode[] }>(
      `/api/evidence-folders/tree?case_id=${caseId}`
    )
    return res.tree
  },

  getContents: (caseId: string, folderId: string | null) =>
    fetchAPI<FolderContentsResponse>(
      `/api/evidence-folders/${folderId || "root"}/contents?case_id=${caseId}`
    ),

  create: (caseId: string, name: string, parentId?: string | null) =>
    fetchAPI<{ id: string; name: string; parent_id: string | null }>(
      "/api/evidence-folders",
      {
        method: "POST",
        body: { case_id: caseId, name, parent_id: parentId || null },
      }
    ),

  rename: (folderId: string, name: string) =>
    fetchAPI<{ id: string; name: string }>(`/api/evidence-folders/${folderId}`, {
      method: "PUT",
      body: { name },
    }),

  delete: (folderId: string, caseId: string) =>
    fetchAPI<{ deleted_files: number; deleted_folders: number }>(
      `/api/evidence-folders/${folderId}?case_id=${caseId}`,
      { method: "DELETE" }
    ),

  move: (folderId: string, newParentId: string | null) =>
    fetchAPI<{ id: string; name: string; parent_id: string | null }>(
      `/api/evidence-folders/${folderId}/move`,
      { method: "PUT", body: { new_parent_id: newParentId } }
    ),

  getProfile: (folderId: string) =>
    fetchAPI<FolderProfile>(`/api/evidence-folders/${folderId}/profile`),

  updateProfile: (
    folderId: string,
    data: { context_instructions?: string | null; profile_overrides?: Record<string, unknown> | null }
  ) =>
    fetchAPI<FolderProfile>(`/api/evidence-folders/${folderId}/profile`, {
      method: "PUT",
      body: data,
    }),

  getEffectiveProfile: (folderId: string, caseId: string) =>
    fetchAPI<EffectiveProfile>(
      `/api/evidence-folders/${folderId}/effective-profile?case_id=${caseId}`
    ),

  processFolder: (
    folderId: string,
    caseId: string,
    recursive = true,
    reprocessCompleted = false
  ) =>
    fetchAPI<{ job_ids: string[]; file_count: number; message: string }>(
      `/api/evidence-folders/${folderId}/process`,
      {
        method: "POST",
        body: { case_id: caseId, recursive, reprocess_completed: reprocessCompleted },
      }
    ),

  moveFile: (fileId: string, newFolderId: string | null) =>
    fetchAPI<{ id: string; folder_id: string | null }>(
      `/api/evidence-folders/files/${fileId}/move?new_folder_id=${newFolderId || ""}`,
      { method: "PUT" }
    ),

  moveFilesBatch: (fileIds: string[], newFolderId: string | null) =>
    fetchAPI<{ moved: number; folder_id: string | null }>(
      `/api/evidence-folders/files/move-batch?new_folder_id=${newFolderId || ""}`,
      { method: "PUT", body: fileIds }
    ),
}
