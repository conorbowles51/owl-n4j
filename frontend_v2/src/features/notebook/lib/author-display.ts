import type { User } from "@/features/auth/auth.types"
import type { NotebookNote } from "../api"

function isPlaceholderName(value?: string | null) {
  return value?.trim().toLowerCase() === "your name"
}

export function isOwnNotebookNote(
  note: Pick<NotebookNote, "author_user_id" | "author_email" | "author_name">,
  user: User | null
) {
  if (!user) return false
  if (note.author_user_id && user.id && note.author_user_id === user.id) return true
  if (note.author_email && user.email && note.author_email === user.email) return true
  if (note.author_email && user.username && note.author_email === user.username) return true
  return Boolean(note.author_name && user.name && note.author_name === user.name)
}

export function notebookAuthorLabel(
  note: Pick<NotebookNote, "author_user_id" | "author_email" | "author_name">,
  user: User | null
) {
  if (isOwnNotebookNote(note, user)) return "You"
  if (note.author_name && !isPlaceholderName(note.author_name)) return note.author_name
  return note.author_email || "User"
}

export function notebookAuthorInitialsSource(
  note: Pick<NotebookNote, "author_user_id" | "author_email" | "author_name">,
  user: User | null
) {
  if (isOwnNotebookNote(note, user)) {
    return user?.name || note.author_name || user?.email || note.author_email || "User"
  }
  return note.author_name || note.author_email || "User"
}
