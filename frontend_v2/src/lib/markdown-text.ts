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
    .replace(/\*\*(.*?)\*\*/g, "$1")
    .replace(/\*(.*?)\*/g, "$1")
    // Underscore emphasis only applies at word boundaries; intra-word
    // underscores (BASE_DATA_INVOICE, 04_email_evidence.pdf) are literal.
    .replace(/(?<![\w])__(?!\s)([\s\S]*?[^\s_])__(?![\w])/g, "$1")
    .replace(/(?<![\w])_(?!\s)([\s\S]*?[^\s_])_(?![\w])/g, "$1")
    .replace(/~~(.*?)~~/g, "$1")
    .replace(/\n+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
}
