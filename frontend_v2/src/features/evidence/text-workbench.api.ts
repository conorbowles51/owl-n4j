import { fetchAPI } from "@/lib/api-client"

/** What read a page or section of a document (services/evidence_page_text.reader_of). */
export interface TextReader {
  kind: string
  words: string
  /** Software or a model read it; the words say so and a quote keeps the label. */
  machine_read: boolean
  model: string | null
  /** OCR's mean confidence, 0 to 100, when it gave one. */
  confidence: number | null
  low_confidence: boolean
}

export interface TextPage {
  page_number: number
  label: string
  start_char: number | null
  end_char: number | null
  text: string
  reader: TextReader | null
  /** Why this page has no text; never shown as blank. */
  text_missing: string | null
}

export interface TextPages {
  evidence_id: string
  case_id: string
  document_name: string
  source_type: string | null
  original_available: boolean
  image_pages: number
  pages_in_step: boolean
  text_version: string | null
  read_at: string | null
  character_count: number
  text_absent: string | null
  page_image_failure: string | null
  page_count: number
  page_offset: number
  page_limit: number
  has_more: boolean
  pages: TextPage[]
}

export interface PassageLocation {
  state: "unchanged" | "moved" | "not_found" | "text_gone"
  words: string | null
  quote: string
  reader: TextReader | null
  taken_page: number | null
  page_number: number | null
  start_char: number | null
  end_char: number | null
}

export interface PageRect {
  x: number
  y: number
  width: number
  height: number
}

/** The window of pages holding `page`: one request serves several page turns. */
export const WINDOW_PAGES = 5

export const QUOTE_MAX_CHARACTERS = 5_000

export function windowOffset(page: number): number {
  return Math.floor((page - 1) / WINDOW_PAGES) * WINDOW_PAGES
}

export const textWorkbenchAPI = {
  pages: (evidenceId: string, pageOffset: number, signal?: AbortSignal) =>
    fetchAPI<TextPages>(`/api/evidence/${evidenceId}/text-pages?page_offset=${pageOffset}&page_limit=${WINDOW_PAGES}`, { signal }),
  /** The page holding a character of the stored text (a hit in a file with no pages of its own). */
  pageAt: (evidenceId: string, character: number, signal?: AbortSignal) =>
    fetchAPI<{ page_number: number | null }>(`/api/evidence/${evidenceId}/text-page-at?character=${character}`, { signal }),
  positions: (evidenceId: string, page: number, words: string, signal?: AbortSignal) =>
    fetchAPI<{ available: boolean; rects: PageRect[] }>(
      `/api/evidence/${evidenceId}/page/${page}/text-positions?${new URLSearchParams({ q: words })}`,
      { signal }
    ),
  passage: (evidenceId: string, targetId: string, signal?: AbortSignal) =>
    fetchAPI<PassageLocation>(`/api/evidence/${evidenceId}/passage?${new URLSearchParams({ target_id: targetId })}`, { signal }),
}
