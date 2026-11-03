import { unified } from "unified"
import remarkParse from "remark-parse"
import remarkGfm from "remark-gfm"
import type { Nodes, RootContent } from "mdast"
import { parseCitation } from "@/lib/citations"

export interface DocumentCitation {
  /** the filename for a citation by name; the evidence file id for doc://<id> */
  filename: string
  page?: number
  evidenceFileId?: string
}

export interface SummarySource {
  number: number
  filename: string
  pages: number[]
  evidenceFileId?: string
}

/** A document citation (doc:// or the older evidence://), read by the one citation parser (lib/citations). */
export function parseDocumentCitation(
  href: string | undefined
): DocumentCitation | null {
  const citation = parseCitation(href)
  if (!citation || citation.scheme !== "doc") return null
  return citation.byName
    ? { filename: citation.target, page: citation.page }
    : { filename: citation.target, page: citation.page, evidenceFileId: citation.target }
}

const parser = unified().use(remarkParse).use(remarkGfm)

function visit(node: Nodes, callback: (node: Nodes) => void) {
  callback(node)
  if ("children" in node) {
    for (const child of node.children) visit(child, callback)
  }
}

function headingText(node: Nodes): string {
  if (node.type === "text") return node.value
  return "children" in node ? node.children.map(headingText).join("") : ""
}

/** Derive display citations from Markdown, never from the entity's source metadata. */
export function collectSummarySources(content: string) {
  const tree = parser.parse(content)
  const definitions = new Map<string, string>()
  visit(tree, (node) => {
    if (node.type === "definition" && !definitions.has(node.identifier)) {
      definitions.set(node.identifier, node.url)
    }
  })
  const citationFor = (node: Nodes) =>
    parseDocumentCitation(
      node.type === "link"
        ? node.url
        : node.type === "linkReference"
          ? definitions.get(node.identifier)
          : undefined
    )

  // Consolidate generated bibliographies only when they contain source links
  // and punctuation. Preserve prose, external references, and unfamiliar formats.
  function isSourceList(node: Nodes): boolean {
    if (citationFor(node)) return true
    if (node.type === "text") return /^[\s,;:.()[\]–—-]*$/.test(node.value)
    if (
      ["list", "listItem", "paragraph", "strong", "emphasis"].includes(
        node.type
      ) &&
      "children" in node
    ) {
      return node.children.every(isSourceList)
    }
    return false
  }

  const bibliographyNodes = new Set<RootContent>()
  const removedRanges: Array<{ start: number; end: number }> = []
  for (let index = 0; index < tree.children.length; index++) {
    const heading = tree.children[index]
    if (
      heading.type !== "heading" ||
      !/^(source references|sources|summary sources)\s*:?$/i.test(
        headingText(heading).trim()
      )
    )
      continue
    let end = index + 1
    while (end < tree.children.length) {
      const next = tree.children[end]
      if (next.type === "heading" && next.depth <= heading.depth) break
      end++
    }
    const section = tree.children.slice(index + 1, end)
    let hasCitation = false
    for (const node of section)
      visit(node, (child) => {
        if (citationFor(child)) hasCitation = true
      })
    if (
      !hasCitation ||
      !section.every((node) => node.type === "definition" || isSourceList(node))
    )
      continue
    for (const node of section) bibliographyNodes.add(node)
    // Keep reference definitions: links elsewhere in the summary may need them.
    for (const node of [
      heading,
      ...section.filter((node) => node.type !== "definition"),
    ]) {
      const start = node.position?.start.offset
      const finish = node.position?.end.offset
      if (start !== undefined && finish !== undefined)
        removedRanges.push({ start, end: finish })
    }
    index = end - 1
  }

  const sources: SummarySource[] = []
  const byFilename = new Map<string, SummarySource>()
  function collect(node: Nodes) {
    visit(node, (child) => {
      const citation = citationFor(child)
      if (!citation) return
      let source = byFilename.get(citation.filename)
      if (!source) {
        source = {
          number: sources.length + 1,
          // a citation by id names its file in the link text
          filename: citation.evidenceFileId ? headingText(child).trim() || "Source file" : citation.filename,
          pages: [],
          ...(citation.evidenceFileId ? { evidenceFileId: citation.evidenceFileId } : {}),
        }
        sources.push(source)
        byFilename.set(citation.filename, source)
      }
      if (citation.page !== undefined && !source.pages.includes(citation.page))
        source.pages.push(citation.page)
    })
  }
  // Number in narrative order, then retain sources listed only in an existing bibliography.
  for (const node of tree.children)
    if (!bibliographyNodes.has(node)) collect(node)
  for (const node of tree.children)
    if (bibliographyNodes.has(node)) collect(node)
  for (const source of sources) source.pages.sort((a, b) => a - b)

  let displayContent = content
  for (const range of removedRanges.sort((a, b) => b.start - a.start)) {
    displayContent =
      displayContent.slice(0, range.start) + displayContent.slice(range.end)
  }
  return {
    content: displayContent,
    sources,
    numbers: new Map(sources.map((source) => [source.evidenceFileId ?? source.filename, source.number])),
  }
}
