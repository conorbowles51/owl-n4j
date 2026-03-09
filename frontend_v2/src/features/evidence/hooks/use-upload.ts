import { useState, useCallback } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { evidenceAPI } from "../api"

interface UploadState {
  files: File[]
  uploading: boolean
  progress: number // 0-100
  error: string | null
}

export function useUpload(caseId: string) {
  const queryClient = useQueryClient()
  const [state, setState] = useState<UploadState>({
    files: [],
    uploading: false,
    progress: 0,
    error: null,
  })

  const addFiles = useCallback((files: File[]) => {
    setState((prev) => ({
      ...prev,
      files: [...prev.files, ...files],
      error: null,
    }))
  }, [])

  const removeFile = useCallback((index: number) => {
    setState((prev) => ({
      ...prev,
      files: prev.files.filter((_, i) => i !== index),
    }))
  }, [])

  const clearFiles = useCallback(() => {
    setState((prev) => ({ ...prev, files: [], error: null }))
  }, [])

  const uploadMutation = useMutation({
    mutationFn: async (files: File[]) => {
      setState((prev) => ({ ...prev, uploading: true, progress: 0, error: null }))

      // Upload in batches of 10
      const batchSize = 10
      let uploaded = 0
      for (let i = 0; i < files.length; i += batchSize) {
        const batch = files.slice(i, i + batchSize)
        await evidenceAPI.upload(caseId, batch)
        uploaded += batch.length
        setState((prev) => ({
          ...prev,
          progress: Math.round((uploaded / files.length) * 100),
        }))
      }

      return { uploaded }
    },
    onSuccess: () => {
      setState({ files: [], uploading: false, progress: 100, error: null })
      queryClient.invalidateQueries({ queryKey: ["evidence", caseId] })
    },
    onError: (error: Error) => {
      setState((prev) => ({
        ...prev,
        uploading: false,
        error: error.message,
      }))
    },
  })

  const upload = useCallback(() => {
    if (state.files.length > 0) {
      uploadMutation.mutate(state.files)
    }
  }, [state.files, uploadMutation])

  return {
    ...state,
    addFiles,
    removeFile,
    clearFiles,
    upload,
  }
}
