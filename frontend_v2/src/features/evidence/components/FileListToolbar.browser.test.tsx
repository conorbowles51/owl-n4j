import "@/styles/globals.css"
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, expect, it, vi } from "vitest"
import { TooltipProvider } from "@/components/ui/tooltip"
import { FileListToolbar } from "./FileListToolbar"

vi.mock("../hooks/use-upload-to-folder", () => ({
  useUploadToFolder: () => ({ mutate: vi.fn(), isPending: false }),
}))
vi.mock("../hooks/use-guarded-process", () => ({
  useGuardedProcess: () => ({ start: vi.fn(), isChecking: false, isProcessing: false }),
}))
vi.mock("./ProcessHoldDialog", () => ({ ProcessHoldDialog: () => null }))
vi.mock("@/features/financial/components/FinancialAccessProvider", () => ({
  FinancialAccessProvider: ({ children }: { children: React.ReactNode }) => children,
}))
vi.mock("@/features/financial/components/EvidenceFinancialPicker", () => ({ EvidenceFinancialPicker: () => null }))
afterEach(cleanup)

it.each([
  ["Add phone report (folder or ZIP)", "Phone report folder"],
  ["Add phone report (folder or ZIP)", "Phone report ZIP file"],
  ["Upload", "Folder"],
])("choosing %s > %s opens the picker and closes the menu, so the page is not left hidden", async (menu, item) => {
  const opened = vi.spyOn(HTMLInputElement.prototype, "click").mockImplementation(() => {})
  render(
    <TooltipProvider>
      <FileListToolbar caseId="case" onCreateFolder={() => {}} onDeleteFiles={() => {}} />
    </TooltipProvider>
  )
  const trigger = screen.getByRole("button", { name: new RegExp(`^${menu.replace(/[()]/g, "\\$&")}`) })
  fireEvent.pointerDown(trigger, { button: 0, pointerType: "mouse" })
  fireEvent.click(await screen.findByRole("menuitem", { name: item }))
  expect(opened).toHaveBeenCalledTimes(1)
  await waitFor(() => expect(screen.queryByRole("menu")).toBeNull())
  // the toolbar is reachable again: nothing outside a menu is hidden
  expect(screen.getByRole("button", { name: /^Add phone report/ })).toBeTruthy()
  opened.mockRestore()
})
