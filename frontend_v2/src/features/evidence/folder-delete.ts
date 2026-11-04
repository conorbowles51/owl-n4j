import type { FolderDeleteSummary } from "./folders.api"
import { ApiError } from "@/lib/api-client"

const n = (value: number) => value.toLocaleString("en-US")
const files = (count: number) => `${n(count)} file${count === 1 ? "" : "s"}`

/** What the delete removes, in words: every file in the folder and its subfolders, as the server counts them. With
 * Deleted items switched on (server setting, off by default) the files are kept 30 days and can be restored. */
export function describeFolderDelete(summary: FolderDeleteSummary, deletedItems = false) {
  const where =
    summary.subfolder_count > 0
      ? `in this folder and its ${n(summary.subfolder_count)} subfolder${summary.subfolder_count === 1 ? "" : "s"}`
      : "in this folder"
  if (summary.file_count === 0) return `There are no files ${where}.`
  const hidden = summary.file_count - summary.listed_file_count
  return (
    (deletedItems
      ? `${files(summary.file_count)} ${where} will be moved to Deleted items (the case owner or an admin can restore ` +
        "them for 30 days, then they are removed for good). The folder itself is removed; a restored file goes back " +
        "to the top of Evidence unless its folder is made again."
      : `${files(summary.file_count)} ${where} will be permanently deleted from disk and database.`) +
    (hidden > 0
      ? ` ${n(hidden)} of them ${hidden === 1 ? "is an internal copy or phone thread document" : "are internal copies or phone thread documents"} not listed in Evidence.`
      : "")
  )
}

/** A refused Delete Folder in plain words; the folder is kept. */
export function folderDeleteRefusal(error: Error) {
  if (error instanceof ApiError && error.status === 403)
    return "You can view this case's evidence but your account cannot delete it, so the folder and its files were kept. Ask the case owner for permission to delete evidence."
  return `${error.message || "The folder could not be deleted."} The folder and its files were kept.`
}
