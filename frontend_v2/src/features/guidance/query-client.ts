import type { QueryClient } from "@tanstack/react-query"

/**
 * The app's query client, for code outside React that names an item from data already loaded (a merge's result,
 * a step's label). Set once by the case guidance layer.
 */
let client: QueryClient | null = null
export const setGuidanceQueryClient = (qc: QueryClient) => {
  client = qc
}
export const guidanceQueryClient = () => client
