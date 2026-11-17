import type { GuideSource } from "@/components/ui/guide-dialog"

const dir = `${import.meta.env.BASE_URL}docs/`

/** The one glossary of terms the app shows (public/docs/glossary.md). Each term is a `##` heading. */
export const GLOSSARY_GUIDE: GuideSource = {
  id: "glossary",
  label: "Glossary",
  title: "Glossary",
  url: `${dir}glossary.md`,
  directory: dir,
  heading: "# Glossary",
  prefix: "glossary",
}

/** A glossary term's anchor: its heading in lower case, words joined by "-" (as GuideDialog builds heading ids). */
export function termAnchor(term: string): string {
  return term
    .toLowerCase()
    .replace(/[^a-z0-9\s-]/g, "")
    .trim()
    .replace(/\s+/g, "-")
}
