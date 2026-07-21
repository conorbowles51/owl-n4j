import { useEffect, useState } from "react"
import { useInfiniteQuery } from "@tanstack/react-query"
import { evidenceAPI } from "../api"

export function useDebouncedValue<T>(value: T, delay: number): T {
  const [debounced, setDebounced] = useState(value)

  useEffect(() => {
    const timeout = window.setTimeout(() => setDebounced(value), delay)
    return () => window.clearTimeout(timeout)
  }, [delay, value])

  return debounced
}

export function useEvidenceTextSearch(caseId: string, rawQuery: string) {
  const trimmedQuery = rawQuery.trim()
  const debouncedQuery = useDebouncedValue(trimmedQuery, 350)

  const query = useInfiniteQuery({
    queryKey: ["evidence-text-search", caseId, debouncedQuery],
    queryFn: ({ pageParam, signal }) =>
      evidenceAPI.searchText(caseId, debouncedQuery, 25, pageParam, signal),
    initialPageParam: 0,
    getNextPageParam: (page) =>
      page.has_more_documents
        ? page.document_offset + page.returned_documents
        : undefined,
    enabled: debouncedQuery.length >= 2,
  })

  return {
    ...query,
    debouncedQuery,
    isDebouncing: trimmedQuery !== debouncedQuery,
  }
}
