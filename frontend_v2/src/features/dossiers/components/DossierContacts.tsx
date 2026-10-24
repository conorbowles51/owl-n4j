import { useState } from "react"
import { Mail, MapPin, Phone, Plus } from "lucide-react"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { dossiersAPI, type Dossier, type DossierContact } from "../api"
import { useDossierMutation } from "../hooks"
import { DossierEvidencePicker } from "./DossierEvidencePicker"

const icons = { phone: Phone, email: Mail, address: MapPin }

function ContactsEditor({
  dossier,
  onClose,
}: {
  dossier: Dossier
  onClose: () => void
}) {
  const [contacts, setContacts] = useState<DossierContact[]>(
    (dossier.contacts ?? []).map((item) => ({ ...item }))
  )
  const [error, setError] = useState("")
  const [sourceFor, setSourceFor] = useState<number | null>(null)
  const update = useDossierMutation<void>(dossier.case_id, dossier.id, () =>
    dossiersAPI.update(dossier.id, { contacts })
  )
  const change = (index: number, patch: Partial<DossierContact>) =>
    setContacts((items) =>
      items.map((item, at) => (at === index ? { ...item, ...patch } : item))
    )
  const save = async (event: React.FormEvent) => {
    event.preventDefault()
    setError("")
    try {
      await update.mutateAsync()
      onClose()
    } catch {
      setError(
        "Contact details could not be saved. Your changes are kept here; try again."
      )
    }
  }
  return (
    <Dialog
      open
      onOpenChange={(value) => {
        if (!value && !update.isPending) onClose()
      }}
    >
      <DialogContent className="max-h-[calc(100dvh-2rem)] overflow-y-auto sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>Contact details for {dossier.display_name}</DialogTitle>
          <DialogDescription>
            Record phone numbers, emails and addresses. You can link a source
            file for each detail.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={(event) => void save(event)} className="space-y-4">
          {contacts.map((contact, index) => (
            <fieldset
              key={contact.id ?? index}
              disabled={update.isPending}
              className="space-y-2 rounded-lg border p-3"
            >
              <legend className="px-1 text-xs font-semibold">
                Contact {index + 1}
              </legend>
              <div className="grid grid-cols-2 gap-2">
                <div className="space-y-1">
                  <Label htmlFor={`contact-kind-${index}`}>Type</Label>
                  <select
                    id={`contact-kind-${index}`}
                    className="h-9 w-full rounded-md border bg-background px-2 text-sm"
                    value={contact.kind}
                    onChange={(event) =>
                      change(index, {
                        kind: event.target.value as DossierContact["kind"],
                      })
                    }
                  >
                    <option value="phone">Phone</option>
                    <option value="email">Email</option>
                    <option value="address">Address</option>
                  </select>
                </div>
                <div className="space-y-1">
                  <Label htmlFor={`contact-label-${index}`}>
                    Label (optional)
                  </Label>
                  <Input
                    id={`contact-label-${index}`}
                    value={contact.label ?? ""}
                    onChange={(event) =>
                      change(index, { label: event.target.value })
                    }
                    placeholder="Work, mobile, home…"
                    maxLength={128}
                  />
                </div>
              </div>
              <div className="space-y-1">
                <Label htmlFor={`contact-value-${index}`}>Value</Label>
                <Input
                  id={`contact-value-${index}`}
                  required
                  maxLength={2000}
                  value={contact.value}
                  onChange={(event) =>
                    change(index, { value: event.target.value })
                  }
                />
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <Button
                  type="button"
                  size="sm"
                  variant="ghost"
                  onClick={() =>
                    setSourceFor(sourceFor === index ? null : index)
                  }
                >
                  {contact.evidence_file_id
                    ? "Change linked source"
                    : "Link source (optional)"}
                </Button>
                {contact.evidence_file_id && (
                  <Button
                    type="button"
                    size="sm"
                    variant="ghost"
                    onClick={() => change(index, { evidence_file_id: null })}
                  >
                    Unlink source
                  </Button>
                )}
                <Button
                  type="button"
                  size="sm"
                  variant="ghost"
                  className="ml-auto text-destructive"
                  onClick={() => {
                    setContacts((items) =>
                      items.filter((_, at) => at !== index)
                    )
                    setSourceFor(null)
                  }}
                >
                  Remove contact
                </Button>
              </div>
              {sourceFor === index && (
                <DossierEvidencePicker
                  caseId={dossier.case_id}
                  onSelect={(item) => {
                    change(index, { evidence_file_id: item.id })
                    setSourceFor(null)
                  }}
                />
              )}
            </fieldset>
          ))}
          <Button
            type="button"
            size="sm"
            variant="outline"
            disabled={contacts.length >= 100 || update.isPending}
            onClick={() =>
              setContacts((items) => [...items, { kind: "phone", value: "" }])
            }
          >
            <Plus className="size-3.5" /> Add contact
          </Button>
          {error && (
            <p role="alert" className="text-sm text-destructive">
              {error}
            </p>
          )}
          <DialogFooter>
            <Button
              type="button"
              variant="ghost"
              disabled={update.isPending}
              onClick={onClose}
            >
              Cancel
            </Button>
            <Button type="submit" variant="primary" disabled={update.isPending}>
              {update.isPending ? "Saving…" : "Save contact details"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

export function DossierContacts({
  dossier,
  canEdit,
  onOpenSource,
}: {
  dossier: Dossier
  canEdit: boolean
  onOpenSource: (id: string) => void
}) {
  const [editing, setEditing] = useState(false)
  return (
    <section className="space-y-3">
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          Contact information
        </h3>
        {canEdit && (
          <Button size="sm" variant="outline" onClick={() => setEditing(true)}>
            {dossier.contacts?.length ? "Edit contacts" : "Add contacts"}
          </Button>
        )}
      </div>
      {dossier.contacts?.length ? (
        <div className="divide-y rounded-lg border">
          {dossier.contacts.map((contact, index) => {
            const Icon = icons[contact.kind]
            return (
              <div
                key={contact.id ?? index}
                className="flex items-start gap-3 p-3"
              >
                <Icon className="mt-1 size-4 shrink-0 text-muted-foreground" />
                <div className="min-w-0 flex-1">
                  <p className="text-xs font-medium">
                    {contact.label || contact.kind}
                  </p>
                  <p className="whitespace-pre-wrap break-all text-sm">
                    {contact.value}
                  </p>
                  <p className="mt-1 text-[11px] text-muted-foreground">
                    {contact.recorded_by_user_id
                      ? "Investigator recorded"
                      : "Saved contact"}
                  </p>
                </div>
                {contact.evidence_file_id && (
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => onOpenSource(contact.evidence_file_id!)}
                  >
                    Open source
                  </Button>
                )}
              </div>
            )
          })}
        </div>
      ) : (
        <p className="text-xs text-muted-foreground">
          No contact details recorded.
        </p>
      )}
      {editing && (
        <ContactsEditor dossier={dossier} onClose={() => setEditing(false)} />
      )}
    </section>
  )
}
