import { useState } from "react"
import { useNavigate } from "react-router-dom"
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu"
import { copyInGesture } from "@/lib/copy-text"
import { labelText } from "../lib/labels"
import { otherParty, pairPath, peoplePath, personPath } from "../lib/participant-menu"
import { identitiesAPI } from "../review/identities.api"
import type { ParticipantLabelData } from "../schemas"
import { ParticipantLabel } from "./ParticipantLabel"

/** Mounted only while the menu is open, so a list row needs no router until someone asks for the menu. */
function MenuItems({ caseId, label, parties, identityKey, onFailed }: {
  caseId: string
  label: ParticipantLabelData
  parties: { from: ParticipantLabelData | null; to: ParticipantLabelData[] }
  identityKey: string
  onFailed: (words: string) => void
}) {
  const navigate = useNavigate()
  const pair = pairPath(caseId, identityKey, otherParty(parties, label))
  const openPeople = async () => {
    try {
      const d = await identitiesAPI.get(caseId, identityKey)
      navigate(peoplePath(caseId, identityKey, d.linked_dossier?.id ?? null))
    } catch (e) {
      onFailed(e instanceof Error && e.message ? e.message : "This person could not be opened.")
    }
  }
  return (
    <>
      <DropdownMenuItem onSelect={() => navigate(personPath(caseId, identityKey))}>Show all with this person</DropdownMenuItem>
      <DropdownMenuItem disabled={!pair} title={pair ? undefined : "This row names no second person."} onSelect={() => pair && navigate(pair)}>Show this pair</DropdownMenuItem>
      <DropdownMenuItem onSelect={() => void openPeople()}>Open in People</DropdownMenuItem>
    </>
  )
}

/**
 * A participant label with its menu (03 section 6.7): Show all with this person, Show this pair, Open in People and
 * Copy name and number. Copy runs inside the click, which is what works on the plain http address.
 */
export function ParticipantMenu({ caseId, label, parties }: {
  caseId: string
  label: ParticipantLabelData | null
  parties: { from: ParticipantLabelData | null; to: ParticipantLabelData[] }
}) {
  const [note, setNote] = useState<string | null>(null)
  if (!label) return <ParticipantLabel label={label} />
  const copy = () => setNote(copyInGesture({ text: labelText(label) }) ? "Copied." : "The browser refused the copy.")
  return (
    <span onClick={(e) => e.stopPropagation()}>
      <DropdownMenu onOpenChange={(open) => open && setNote(null)}>
        <DropdownMenuTrigger className="text-left hover:underline" aria-label={`Actions for ${labelText(label)}`}>
          <ParticipantLabel label={label} />
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start">
          {label.identity_key ? (
            <MenuItems caseId={caseId} label={label} parties={parties} identityKey={label.identity_key} onFailed={setNote} />
          ) : (
            <DropdownMenuItem disabled>No identifier recorded, so only the name can be copied</DropdownMenuItem>
          )}
          <DropdownMenuItem onSelect={copy}>Copy name and number</DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
      {note && <span role="status" className="ml-1 text-xs text-muted-foreground">{note}</span>}
    </span>
  )
}
