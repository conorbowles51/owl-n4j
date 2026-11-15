/** What a row whose stored file is gone says, in the list and where its preview would be. */
export function fileMissingText(since: string): string {
  const date = new Date(since)
  const when = Number.isNaN(date.getTime()) ? "" : ` (found ${date.toLocaleDateString()})`
  return `File missing from the server${when}: upload it again to restore. The record and what was read from it are kept; until then the file cannot be opened or processed.`
}
