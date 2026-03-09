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
          const mapped: SimilarPair[] = rawPairs.map((p: any) => ({
            key1: p.entity1?.key ?? p.key1,
            name1: p.entity1?.name ?? p.name1,
            type1: p.entity1?.type ?? p.type1,
            key2: p.entity2?.key ?? p.key2,
            name2: p.entity2?.name ?? p.name2,
            type2: p.entity2?.type ?? p.type2,
            similarity: p.similarity,
          }))
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
