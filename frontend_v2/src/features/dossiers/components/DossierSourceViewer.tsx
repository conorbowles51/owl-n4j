import { useQuery } from "@tanstack/react-query"
import { DocumentViewer } from "@/components/ui/document-viewer"
import { evidenceAPI } from "@/features/evidence/api"

export interface DossierSource {
  evidenceId: string
  name: string
  page?: number
  time?: number
}

export function DossierSourceViewer({
  caseId,
  source,
  onClose,
}: {
  caseId: string
  source: DossierSource | null
  onClose: () => void
}) {
  const file = useQuery({
    queryKey: ["evidence", "detail", source?.evidenceId],
    queryFn: () => evidenceAPI.get(source!.evidenceId),
    enabled: Boolean(source),
  })
  return (
    <DocumentViewer
      caseId={caseId}
      evidenceId={source?.evidenceId}
      open={Boolean(source)}
      onOpenChange={(open) => {
        if (!open) onClose()
      }}
      documentUrl={
        source ? evidenceAPI.getFileUrl(source.evidenceId) : undefined
      }
      documentName={file.data?.original_filename ?? source?.name}
      initialPage={source?.page}
      initialTime={source?.time}
      navigationKey={
        source
          ? `${source.evidenceId}:${source.page ?? 1}:${source.time ?? ""}`
          : ""
      }
      transcription={file.data?.transcription}
      transcriptionSegments={file.data?.transcription_segments}
      transcriptSpeakers={file.data?.transcription_speakers}
      transcriptSpeakerMerges={file.data?.transcription_speaker_merges}
    />
  )
}
