/** What a row whose stored file is gone says, in the list and where its preview would be. */
export function fileMissingText(since: string): string {
  const date = new Date(since)
  const when = Number.isNaN(date.getTime()) ? "" : ` (found ${date.toLocaleDateString()})`
  return `The stored file is missing from the server${when}. The record is kept, but the file cannot be opened or processed until it is supplied again.`
}
