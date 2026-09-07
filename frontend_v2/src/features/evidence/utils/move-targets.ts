import type { FolderTreeNode } from "@/types/evidence.types"

export type MoveSource =
  | { kind: "files"; files: { id: string; folder_id: string | null }[] }
  | { kind: "folder"; id: string; name: string; parent_id: string | null }

export function flattenFolders(
  tree: FolderTreeNode[],
  depth = 0,
  parentPath = "Evidence root"
): (FolderTreeNode & { depth: number; path: string })[] {
  return tree.flatMap((folder) => {
    const path = `${parentPath} / ${folder.name}`
    return [
      { ...folder, depth, path },
      ...flattenFolders(folder.children, depth + 1, path),
    ]
  })
}

export function invalidMoveReason(
  source: MoveSource,
  destination: string | null,
  folders: Pick<FolderTreeNode, "id" | "name" | "parent_id">[]
): string | null {
  const byId = new Map(folders.map((folder) => [folder.id, folder]))
  if (destination !== null && !byId.has(destination))
    return "Folder no longer exists"
  if (source.kind === "files")
    return source.files.every((file) => file.folder_id === destination)
      ? "Already in this folder"
      : null
  if (source.parent_id === destination) return "Already in this folder"
  let current = destination
  const seen = new Set<string>()
  while (current) {
    if (current === source.id || seen.has(current))
      return "Cannot move into itself or a subfolder"
    seen.add(current)
    current = byId.get(current)?.parent_id ?? null
  }
  if (
    folders.some(
      (folder) =>
        folder.id !== source.id &&
        folder.parent_id === destination &&
        folder.name === source.name
    )
  )
    return "A folder with this name already exists here"
  return null
}
