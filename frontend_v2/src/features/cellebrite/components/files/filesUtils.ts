import {
  CheckCircle2,
  File,
  FileText,
  Film,
  Folder,
  Globe,
  Image,
  Mail,
  MessageSquare,
  Music,
  Phone,
  Tag,
  User,
} from "lucide-react"

import type { CellebriteRecord, FileTreeNode } from "../../types"
import { asText, readList, readNumber, readText } from "../shared/cellebrite-format"

export type FilesGroupBy = "category" | "parent" | "app" | "path"
export type FilesLayout = "grid" | "list"

export type CellebriteFileRecord = CellebriteRecord & {
  id?: string
  original_filename?: string
  filename?: string
  size?: number
  sha256?: string
  status?: string
  tags?: string[]
  linked_entity_ids?: string[]
  is_relevant?: boolean
  cellebrite_category?: string
  cellebrite_report_key?: string
  parent?: CellebriteRecord | null
  device_path_segments?: string[]
}

export type EvidenceTagCount = {
  tag: string
  count: number
}

export type FileTreeSelection = {
  key: string | null
  label: string
  filter: CellebriteRecord
}

export const GROUP_BY_OPTIONS: { key: FilesGroupBy; label: string }[] = [
  { key: "category", label: "Category" },
  { key: "parent", label: "Parent entity" },
  { key: "app", label: "Source app" },
  { key: "path", label: "Device path" },
]

export const CATEGORY_COLORS: Record<string, string> = {
  Image: "#06b6d4",
  Audio: "#10b981",
  Video: "#8b5cf6",
  Text: "#f59e0b",
  Other: "#64748b",
}

export const CATEGORY_ICONS = {
  Image,
  Audio: Music,
  Video: Film,
  Text: FileText,
  Other: File,
}

export const PARENT_ICONS = {
  Person: User,
  Contact: User,
  Communication: MessageSquare,
  PhoneCall: Phone,
  Email: Mail,
  VisitedPage: Globe,
  Unlinked: Folder,
}

export function fileId(file: CellebriteFileRecord): string {
  return readText(file, ["id", "file_id", "evidence_id"], "file")
}

export function fileName(file: CellebriteFileRecord): string {
  return readText(file, ["original_filename", "filename", "name"], fileId(file))
}

export function fileCategory(file: CellebriteFileRecord): string {
  return readText(file, ["cellebrite_category", "category", "type"], "Other")
}

export function fileSize(file: CellebriteFileRecord): string {
  const size = readNumber(file, ["size", "file_size"], Number.NaN)
  if (!Number.isFinite(size)) return ""
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  if (size < 1024 * 1024 * 1024) return `${(size / (1024 * 1024)).toFixed(1)} MB`
  return `${(size / (1024 * 1024 * 1024)).toFixed(1)} GB`
}

export function evidenceUrl(id: string): string {
  return `/api/evidence/${encodeURIComponent(id)}/file`
}

export function videoFrameUrl(id: string): string {
  return `/api/evidence/${encodeURIComponent(id)}/frames/frame_0001.jpg`
}

export function categoryColor(category: string): string {
  return CATEGORY_COLORS[category] ?? CATEGORY_COLORS.Other
}

export function fileTags(file: CellebriteFileRecord): string[] {
  return readList(file, ["tags"])
}

export function linkedEntityIds(file: CellebriteFileRecord): string[] {
  return readList(file, ["linked_entity_ids"])
}

export function reportKeyOfFile(file: CellebriteFileRecord): string {
  return readText(file, ["cellebrite_report_key", "report_key", "device_report_key"])
}

export function captureDate(file: CellebriteFileRecord): string {
  return readText(file, ["capture_time", "creation_time", "created_at", "timestamp"])
}

export function hasGeotag(file: CellebriteFileRecord): boolean {
  return Boolean(file.has_geotag ?? file.latitude ?? file.longitude ?? file.lat ?? file.lng)
}

export function selectedFilterValue(selection: FileTreeSelection | null, key: string): string {
  if (!selection?.filter) return ""
  return asText(selection.filter[key])
}

export function treeNodeKey(node: FileTreeNode): string {
  return readText(node, ["key", "value", "label"], node.label)
}

export function treeSelectionFromNode(node: FileTreeNode | null): FileTreeSelection {
  if (!node) return { key: null, label: "All files", filter: {} }
  const key = treeNodeKey(node)
  const filter = node.filter && typeof node.filter === "object" && !Array.isArray(node.filter)
    ? (node.filter as CellebriteRecord)
    : {}
  return { key, label: node.label, filter }
}

export function fileParentLabel(file: CellebriteFileRecord): string {
  const parent = file.parent
  if (!parent || typeof parent !== "object" || Array.isArray(parent)) return ""
  return readText(parent, ["label", "type", "name"])
}

export function fileBadges(file: CellebriteFileRecord) {
  return [
    file.is_relevant ? { key: "relevant", label: "Relevant", icon: CheckCircle2, color: "text-emerald-500" } : null,
    fileTags(file).length ? { key: "tags", label: "Tagged", icon: Tag, color: "text-amber-500" } : null,
    linkedEntityIds(file).length ? { key: "entities", label: "Linked", icon: User, color: "text-blue-500" } : null,
  ].filter(Boolean)
}
