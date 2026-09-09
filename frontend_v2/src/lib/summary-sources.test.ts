import { describe, expect, it } from "vitest"
import { collectSummarySources, parseDocumentCitation } from "./summary-sources"

describe("summary source display model", () => {
  it("numbers documents in first-citation order and groups repeated pages and URI encodings", () => {
    const model =
      collectSummarySources(`Transfers [long name.pdf](doc://long%20name.pdf/4).
Withdrawal [other](evidence://other.pdf).
Again [same](evidence://long%20name.pdf), [later](doc://long%20name.pdf/12), [repeat](doc://long%20name.pdf/4).`)
    expect(model.sources).toEqual([
      { number: 1, filename: "long name.pdf", pages: [4, 12] },
      { number: 2, filename: "other.pdf", pages: [] },
    ])
    expect(model.numbers.get("long name.pdf")).toBe(1)
  })

  it("supports reference-style citations and tables without treating code, images or ordinary URLs as sources", () => {
    const model = collectSummarySources(`| Fact | Source |
| --- | --- |
| Payment | [statement][BANK] |

[bank]: doc://statement.pdf/7
[unused]: evidence://unused.pdf

\`[code](evidence://code.pdf)\`

\`\`\`md
[example](doc://example.pdf/4)
\`\`\`

![image](evidence://image.png) [website](https://example.com) plain-filename.pdf`)
    expect(model.sources).toEqual([
      { number: 1, filename: "statement.pdf", pages: [7] },
    ])
    expect(model.content).toContain("plain-filename.pdf")
  })

  it("consolidates generated bibliographies while retaining their links and reference definitions", () => {
    const model = collectSummarySources(`## Source References
- [Listed first](evidence://bibliography.pdf)
- [Narrative file](evidence://narrative.pdf)

[bank]: doc://narrative.pdf/3

## Findings
The account [statement][bank] received a transfer.

## Sources
- [Repeated](doc://narrative.pdf/3)`)
    expect(model.sources).toEqual([
      { number: 1, filename: "narrative.pdf", pages: [3] },
      { number: 2, filename: "bibliography.pdf", pages: [] },
    ])
    expect(model.content).not.toContain("## Source References")
    expect(model.content).not.toContain("## Sources")
    expect(model.content).toContain("[bank]: doc://narrative.pdf/3")
    expect(model.content).toContain("## Findings")
  })

  it("preserves source sections containing substantive text or external references", () => {
    const content = `## Sources
- [Report](doc://report.pdf/2) disputes the timeline.
- [Website](https://example.com)

## Notes
Keep this text.`
    expect(collectSummarySources(content).content).toBe(content)
  })

  it("does not invent citations for legacy plain text and restarts numbering for each summary", () => {
    expect(
      collectSummarySources("A finding from old-file.pdf.").sources
    ).toEqual([])
    expect(collectSummarySources("").sources).toEqual([])
    collectSummarySources(
      "[first](evidence://first.pdf) [second](evidence://second.pdf)"
    )
    expect(
      collectSummarySources("[next](evidence://next.pdf)").sources[0].number
    ).toBe(1)
  })

  it("decodes filenames safely, preserves paths and validates page numbers", () => {
    expect(
      parseDocumentCitation("doc://folder%2F100%25%20report.pdf/8")
    ).toEqual({ filename: "folder/100% report.pdf", page: 8 })
    expect(parseDocumentCitation("evidence://100%report.pdf")).toEqual({
      filename: "100%report.pdf",
      page: undefined,
    })
    expect(parseDocumentCitation("doc://folder/report.pdf")).toEqual({
      filename: "folder/report.pdf",
      page: undefined,
    })
    expect(parseDocumentCitation("doc://report.pdf/0")).toEqual({
      filename: "report.pdf",
      page: undefined,
    })
    expect(parseDocumentCitation("evidence://")).toBeNull()
    expect(parseDocumentCitation("javascript:alert(1)")).toBeNull()
  })
})
