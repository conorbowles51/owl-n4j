import { useLocation, useNavigate } from "react-router-dom"
import { GuideDialog } from "@/components/ui/guide-dialog"
import { PHONE_GUIDES } from "./guide"

/**
 * /guide/phones: the phone Guide opened on its own, the target of every "Learn more" link on a mark.
 * With a #term it opens on the Glossary at that term; closing it returns to the screen the link was on.
 */
export default function PhoneGuidePage() {
  const { hash } = useLocation()
  const navigate = useNavigate()
  const anchor = hash.replace(/^#/, "") || undefined
  return (
    <div className="flex h-full flex-col items-start gap-3 p-6">
      <h1 className="text-lg font-semibold">Phone guide</h1>
      <p className="text-sm text-muted-foreground">The phone user guide, team checklist and glossary.</p>
      <GuideDialog
        guides={PHONE_GUIDES}
        defaultOpen
        initial={anchor ? "glossary" : "user"}
        anchor={anchor}
        onOpenChange={(open) => {
          if (!open && window.history.length > 1) navigate(-1)
        }}
      />
    </div>
  )
}
