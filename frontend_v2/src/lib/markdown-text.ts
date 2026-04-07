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
    .replace(/(\*\*|__)(.*?)\1/g, "$2")
    .replace(/(\*|_)(.*?)\1/g, "$2")
    .replace(/~~(.*?)~~/g, "$1")
    .replace(/\n+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
}
