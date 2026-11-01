/**
 * One copy helper for plain http (07 4.10). The page runs in an insecure context, where the async clipboard API
 * is missing, so copying happens inside the user's click through the copy event (plain text and HTML together).
 * Up to IN_CLICK_LIMIT rows are copied in the same click. Larger copies take two steps: the text is prepared,
 * then a second click copies it ("12,345 messages are ready to copy. Copy now."). If the browser still refuses,
 * the caller shows the text selected with "Press Ctrl+C". Graph "Copy Key" and Chat use the same helper.
 */

export const IN_CLICK_LIMIT = 5_000

export interface CopyPayload {
  text: string
  html?: string
}

/** Must be called synchronously inside a user gesture (a click or key handler). Returns true when copied. */
export function copyInGesture(payload: CopyPayload, doc: Document = document): boolean {
  let wrote = false
  const onCopy = (event: ClipboardEvent) => {
    if (!event.clipboardData) return
    event.clipboardData.setData("text/plain", payload.text)
    if (payload.html) event.clipboardData.setData("text/html", payload.html)
    event.preventDefault()
    wrote = true
  }
  doc.addEventListener("copy", onCopy as EventListener, { once: true } as AddEventListenerOptions)
  let ran = false
  try {
    ran = typeof doc.execCommand === "function" && doc.execCommand("copy")
  } catch {
    ran = false
  } finally {
    doc.removeEventListener("copy", onCopy as EventListener)
  }
  return ran && wrote
}

/** Selects the element's text so the person can press Ctrl+C (the last fallback). */
export function selectForManualCopy(element: HTMLElement, doc: Document = document): boolean {
  const selection = doc.getSelection?.()
  if (!selection) return false
  const range = doc.createRange()
  range.selectNodeContents(element)
  selection.removeAllRanges()
  selection.addRange(range)
  return true
}

export function needsTwoSteps(rowCount: number): boolean {
  return rowCount > IN_CLICK_LIMIT
}

export function readyToCopySentence(rowCount: number, noun: string): string {
  return `${rowCount.toLocaleString("en-US")} ${noun} are ready to copy. Copy now.`
}

/** Escapes text for the HTML flavour. */
export function htmlEscape(text: string): string {
  return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;")
}
