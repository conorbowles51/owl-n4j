export function markdownToPlainText(markdown: string): string {
  return markdown
    .replace(/\r\n?/g, "\n")
    .replace(/```[\s\S]*?```/g, (block) =>
      block.replace(/^```[^\n]*\n?/, "").replace(/\n?```$/, "")
    )
    .replace(/`([^`]+)`/g, "$1")
    .replace(/!\[([^\]]*)\]\([^)]+\)/g, "$1")
    .replace(/\[([^\]]+)\]\(([^)]+)\)/g, "$1")
    .replace(/^ {0,3}(#{1,6})\s+/gm, "")
    .replace(/^>\s?/gm, "")
    .replace(/^ {0,3}([-+*]|\d+\.)\s+/gm, "")
    .replace(/^ {0,3}([-*_]\s*){3,}$/gm, " ")
    .replace(/(^|[^\w])(\*\*|__)(\S(?:.*?\S)?)\2(?=$|[^\w])/g, "$1$3")
    .replace(/(^|[^\w])(\*|_)(\S(?:.*?\S)?)\2(?=$|[^\w])/g, "$1$3")
    .replace(/~~(.*?)~~/g, "$1")
    .replace(/\n+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
}
