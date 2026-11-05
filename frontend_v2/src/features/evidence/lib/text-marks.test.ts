import { describe, expect, it } from "vitest"
import { markedPieces } from "./text-marks"
import { selectionOffsets } from "./text-selection"
import { passageHref, textWorkbenchHref } from "./text-workbench-link"

describe("markedPieces", () => {
  const joined = (text: string, marks: Parameters<typeof markedPieces>[1]) => markedPieces(text, marks).map((p) => p.text).join("")

  it("keeps the text exactly, in order, whatever the marks", () => {
    const text = "one two three"
    const marks = [{ start: 4, end: 7, kind: "match" as const }, { start: 0, end: 3, kind: "current" as const }]
    expect(joined(text, marks)).toBe(text)
    expect(markedPieces(text, marks).map((p) => p.kind)).toEqual(["current", null, "match", null])
  })

  it("cuts an overlapping mark and ignores one outside the page", () => {
    const text = "abcdef"
    expect(joined(text, [{ start: 0, end: 4, kind: "passage" }, { start: 2, end: 5, kind: "match" }, { start: 20, end: 30, kind: "match" }])).toBe(text)
    expect(markedPieces(text, [{ start: -5, end: -1, kind: "match" }])).toEqual([{ text, kind: null }])
  })

  it("counts an emoji as one character, as the server does", () => {
    expect(markedPieces("😀 Paid £500", [{ start: 2, end: 6, kind: "match" }])).toEqual([
      { text: "😀 ", kind: null }, { text: "Paid", kind: "match" }, { text: " £500", kind: null },
    ])
  })

  it("gives one empty piece for empty text", () => {
    expect(markedPieces("", [])).toEqual([{ text: "", kind: null }])
  })
})

describe("selectionOffsets", () => {
  it("counts characters across marks, with no clipboard API and no secure context", () => {
    const panel = document.createElement("div")
    panel.innerHTML = "<span>Paid to </span><mark>ACME</mark><span> Ltd\n\nWire</span>"
    document.body.append(panel)
    const selection = window.getSelection()!
    const range = document.createRange()
    range.setStart(panel.childNodes[1].firstChild!, 2)
    range.setEnd(panel.childNodes[2].firstChild!, 4)
    selection.removeAllRanges()
    selection.addRange(range)
    expect(selectionOffsets(panel, selection)).toEqual({ start: 10, end: 16 })
    expect(panel.textContent!.slice(10, 16)).toBe("ME Ltd")
    panel.remove()
  })

  it("counts an emoji as one character, as the server does", () => {
    const panel = document.createElement("div")
    panel.textContent = "😀 Paid £500"
    document.body.append(panel)
    const selection = window.getSelection()!
    const range = document.createRange()
    range.setStart(panel.firstChild!, 3)
    range.setEnd(panel.firstChild!, 7)
    selection.removeAllRanges()
    selection.addRange(range)
    expect(selection.toString()).toBe("Paid")
    expect(selectionOffsets(panel, selection)).toEqual({ start: 2, end: 6 })
    panel.remove()
  })

  it("gives nothing for no selection or one outside the panel", () => {
    const panel = document.createElement("div")
    panel.textContent = "inside"
    const other = document.createElement("div")
    other.textContent = "outside"
    document.body.append(panel, other)
    const selection = window.getSelection()!
    selection.removeAllRanges()
    expect(selectionOffsets(panel, selection)).toBeNull()
    const range = document.createRange()
    range.selectNodeContents(other)
    selection.addRange(range)
    expect(selectionOffsets(panel, selection)).toBeNull()
    panel.remove()
    other.remove()
  })
})

describe("links", () => {
  it("opens a quote at its page", () => {
    expect(passageHref("c 1", "file:v:1:2", { page_number: 7 })).toBe("/cases/c%201/evidence/file/text?page=7&passage=file%3Av%3A1%3A2")
    expect(textWorkbenchHref("c", "f")).toBe("/cases/c/evidence/f/text")
  })
})
