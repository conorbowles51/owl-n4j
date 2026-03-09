import { evidenceAPI } from "../../api"

interface PdfPreviewProps {
  evidenceId: string
}

export function PdfPreview({ evidenceId }: PdfPreviewProps) {
  const url = evidenceAPI.getFileUrl(evidenceId)

  return (
    <iframe
      src={url}
      className="h-[500px] w-full rounded-md border border-border"
      title="PDF Preview"
    />
  )
}
