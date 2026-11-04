import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { describe, expect, it, vi } from "vitest"

/** Delete Folder counts every file the delete removes, including files only in subfolders (lx-uploadfollow D), and
 * a refused delete says so in plain words while the folder stays (E). */
const api = vi.hoisted(() => ({ fetchAPI: vi.fn() }))
vi.mock("@/lib/api-client", async (orig) => ({ ...(await orig<object>()), ...api }))

import { ApiError } from "@/lib/api-client"
import { DeleteFolderDialog } from "./DeleteFolderDialog"
import { describeFolderDelete, folderDeleteRefusal } from "../folder-delete"

function show(props: Partial<Parameters<typeof DeleteFolderDialog>[0]> = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const onConfirm = vi.fn()
  render(
    <QueryClientProvider client={client}>
      <DeleteFolderDialog open onOpenChange={() => {}} caseId="case-1" folderId="folder-1" folderName="Phone dump"
        onConfirm={onConfirm} {...props} />
    </QueryClientProvider>,
  )
  return onConfirm
}

describe("Delete Folder", () => {
  it("counts the files in subfolders when the folder itself holds none", async () => {
    api.fetchAPI.mockReset()
    api.fetchAPI.mockResolvedValue({ file_count: 1000, listed_file_count: 1000, subfolder_count: 4 })
    const onConfirm = show()
    expect(await screen.findByText(
      "1,000 files in this folder and its 4 subfolders will be permanently deleted from disk and database.",
    )).toBeTruthy()
    expect(api.fetchAPI).toHaveBeenCalledWith("/api/evidence-folders/folder-1/delete-summary?case_id=case-1")
    fireEvent.click(screen.getByRole("button", { name: "Delete Folder" }))
    expect(onConfirm).toHaveBeenCalled()
  })

  it("does not offer the delete until the files are counted, nor when they could not be", async () => {
    api.fetchAPI.mockReset()
    api.fetchAPI.mockRejectedValue(new ApiError("Internal error", 500))
    show()
    expect((screen.getByRole("button", { name: "Delete Folder" }) as HTMLButtonElement).disabled).toBe(true)
    expect(await screen.findByText(
      "The files in this folder could not be counted, so it cannot be deleted now. Close this and try again.",
    )).toBeTruthy()
    expect((screen.getByRole("button", { name: "Delete Folder" }) as HTMLButtonElement).disabled).toBe(true)
  })

  it("shows why a delete was refused", async () => {
    api.fetchAPI.mockReset()
    api.fetchAPI.mockResolvedValue({ file_count: 2, listed_file_count: 2, subfolder_count: 0 })
    show({ error: folderDeleteRefusal(new ApiError("User does not have evidence.delete permission for case x", 403)) })
    await waitFor(() => expect(screen.getByRole("alert").textContent).toBe(
      "You can view this case's evidence but your account cannot delete it, so the folder and its files were kept. Ask the case owner for permission to delete evidence.",
    ))
  })

  it("puts the count in words, with files Evidence does not list", () => {
    expect(describeFolderDelete({ file_count: 1, listed_file_count: 1, subfolder_count: 0 })).toBe(
      "1 file in this folder will be permanently deleted from disk and database.",
    )
    expect(describeFolderDelete({ file_count: 0, listed_file_count: 0, subfolder_count: 1 })).toBe(
      "There are no files in this folder and its 1 subfolder.",
    )
    expect(describeFolderDelete({ file_count: 1200, listed_file_count: 1000, subfolder_count: 2 })).toBe(
      "1,200 files in this folder and its 2 subfolders will be permanently deleted from disk and database. 200 of them are internal copies or phone thread documents not listed in Evidence.",
    )
    expect(folderDeleteRefusal(new ApiError("This folder holds a statement in use.", 409))).toBe(
      "This folder holds a statement in use. The folder and its files were kept.",
    )
  })
})
