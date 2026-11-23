/**
 * Whether a dialog other than the tour is open. A panel with its own tour (data-guide-panel) is what the tour explains,
 * and so is a window that holds one (the Corroborate panel drawn inside the dossier sheet it was asked from).
 */
export function otherDialogOpen(): boolean {
  if (document.querySelector("[role='alertdialog']")) return true
  return Array.from(document.querySelectorAll<HTMLElement>("[role='dialog']")).some(
    (el) => el.dataset.testid !== "tour-popup" && !el.hasAttribute("data-guide-panel") && !el.querySelector("[data-guide-panel]")
  )
}
