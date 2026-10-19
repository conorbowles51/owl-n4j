/** Keep result order and bound active requests. A failed item refuses the operation. */
export async function boundedMap<T, R>(
  items: T[],
  read: (item: T) => Promise<R>,
  concurrency = 5
): Promise<R[]> {
  const result = new Array<R>(items.length)
  let next = 0
  let failed = false
  await Promise.all(
    Array.from({ length: Math.min(concurrency, items.length) }, async () => {
      while (!failed && next < items.length) {
        const index = next++
        try {
          result[index] = await read(items[index])
        } catch (error) {
          failed = true
          throw error
        }
      }
    })
  )
  return result
}
