import { ApiError, type fetchAPI } from "@/lib/api-client"

type Read = (url: string, options?: Parameters<typeof fetchAPI>[1]) => Promise<unknown> | unknown

/**
 * Browser fixtures answer the statement-import requests the page sends today.
 * A standalone import is queued as a background job (queue-import) and its receipt
 * comes back with the accepted job; fixtures that model the receipt as the answer
 * to `/confirm?` keep doing so. The reading preview of judgement calls has none.
 */
export function importJobs<R extends Read>(read: R): R {
  return (async (url: string, options?: Parameters<typeof fetchAPI>[1]) => {
    const text = String(url)
    if (text.includes("/judgements/preview?")) return { items: [] }
    if (text.includes("/statement-import/") && text.includes("/queue-import?")) {
      try {
        const receipt = await read(text.replace("/queue-import?", "/confirm?"), options)
        return { receipt, operation: { batch_id: "job", status: "completed", outcomes: [] } }
      } catch (error) {
        if (error instanceof ApiError) throw error
        throw new ApiError(error instanceof Error ? error.message : String(error), 409)
      }
    }
    return read(url, options)
  }) as R
}
