import type { GuideSource } from "@/components/ui/guide-dialog"

/** The phone Guide (07 9): user guide, team checklist and glossary, served from public/docs/phone-guide/. */
const dir = `${import.meta.env.BASE_URL}docs/phone-guide/`
export const PHONE_GUIDES: GuideSource[] = [
  { id: "user", label: "User guide", title: "Phone user guide", url: `${dir}phone-user-guide.md`, directory: dir, heading: "# Phone user guide", prefix: "phone-guide" },
  { id: "checklist", label: "Team checklist", title: "Phone team checklist", url: `${dir}phone-team-checklist.md`, directory: dir, heading: "# Phone team checklist", prefix: "phone-checklist" },
  { id: "glossary", label: "Glossary", title: "Phone glossary", url: `${dir}phone-glossary.md`, directory: dir, heading: "# Phone glossary", prefix: "phone-glossary" },
]
