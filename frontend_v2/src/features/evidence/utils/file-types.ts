export type FileTypeCategory = "Image" | "Document" | "Audio" | "Video" | "Data" | "Other"

const EXT_MAP: Record<string, FileTypeCategory> = {
  // Image
  jpg: "Image", jpeg: "Image", png: "Image", gif: "Image", bmp: "Image",
  webp: "Image", svg: "Image", tiff: "Image", tif: "Image", ico: "Image",
  // Document
  pdf: "Document", doc: "Document", docx: "Document", txt: "Document",
  rtf: "Document", odt: "Document", xls: "Document", xlsx: "Document",
  ppt: "Document", pptx: "Document", html: "Document", htm: "Document",
  md: "Document", eml: "Document", msg: "Document",
  // Audio
  mp3: "Audio", wav: "Audio", ogg: "Audio", flac: "Audio", aac: "Audio",
  wma: "Audio", m4a: "Audio", opus: "Audio",
  // Video
  mp4: "Video", avi: "Video", mov: "Video", mkv: "Video", wmv: "Video",
  flv: "Video", webm: "Video", m4v: "Video",
  // Data
  csv: "Data", json: "Data", xml: "Data", tsv: "Data", sql: "Data",
  db: "Data", sqlite: "Data", parquet: "Data",
}

export function getFileTypeCategory(filename: string): FileTypeCategory {
  const ext = filename.split(".").pop()?.toLowerCase() ?? ""
  return EXT_MAP[ext] ?? "Other"
}

export const FILE_TYPE_CATEGORIES: FileTypeCategory[] = [
  "Image", "Document", "Audio", "Video", "Data", "Other",
]
