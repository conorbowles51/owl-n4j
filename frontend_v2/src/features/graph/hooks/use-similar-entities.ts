import { useState, useCallback, useRef } from "react"
import {
  findSimilarEntitiesStream,
  type SimilarEntitiesStreamCallbacks,
} from "../api"
import type { SimilarPair } from "@/types/graph.types"

interface ScanProgress {
  type: string
  compared: number
  total: number
  pairs_found: number
}

export function useSimilarEntities(caseId: string) {
  const [isScanning, setIsScanning] = useState(false)
  const [progress, setProgress] = useState<ScanProgress | null>(null)
  const [currentType, setCurrentType] = useState<string | null>(null)
  const [results, setResults] = useState<SimilarPair[]>([])
  const [error, setError] = useState<string | null>(null)
  const cancelRef = useRef<(() => void) | null>(null)

  const startScan = useCallback(
    (options: {
      entityTypes?: string[] | null
      similarityThreshold?: number
      maxResults?: number
    }) => {
      setIsScanning(true)
      setResults([])
      setError(null)
      setProgress(null)

      const callbacks: SimilarEntitiesStreamCallbacks = {
        onStart: () => setCurrentType(null),
        onTypeStart: (data) => setCurrentType(data.type),
        onProgress: (data) =>
          setProgress({
            type: data.type,
            compared: data.compared,
            total: data.total,
            pairs_found: data.pairs_found,
          }),
        onTypeComplete: () => {},
        onComplete: (data) => {
          const rawPairs = data.limited_results ?? []
          const mapped: SimilarPair[] = rawPairs.map((p: Record<string, unknown>) => {
            const e1 = p.entity1 as Record<string, unknown> | undefined
            const e2 = p.entity2 as Record<string, unknown> | undefined
            return {
              key1: (e1?.key ?? p.key1) as string,
              name1: (e1?.name ?? p.name1) as string,
              type1: (e1?.type ?? p.type1) as string,
              key2: (e2?.key ?? p.key2) as string,
              name2: (e2?.name ?? p.name2) as string,
              type2: (e2?.type ?? p.type2) as string,
              similarity: p.similarity as number,
            }
          })
          setResults(mapped)
          setIsScanning(false)
          setCurrentType(null)
        },
        onError: (err) => {
          setError(err)
          setIsScanning(false)
        },
        onCancelled: () => {
          setIsScanning(false)
          setCurrentType(null)
        },
      }

      cancelRef.current = findSimilarEntitiesStream(
        caseId,
        options,
        callbacks
      )
    },
    [caseId]
  )

  const cancel = useCallback(() => {
    cancelRef.current?.()
    cancelRef.current = null
    setIsScanning(false)
  }, [])

  return {
    isScanning,
    progress,
    currentType,
    results,
    error,
    startScan,
    cancel,
  }
}
