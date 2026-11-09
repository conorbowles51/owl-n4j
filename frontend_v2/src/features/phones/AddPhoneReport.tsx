import { Smartphone } from "lucide-react"
import { Link } from "react-router-dom"
import { Button } from "@/components/ui/button"

/**
 * What a case with no phone shows on its Phones page: what a phone report is, what can be added and how big it can
 * be, and the way in. Adding goes through the Evidence upload ("Add phone report (folder or ZIP)"), the one path
 * that reads and checks a report, so this page opens Evidence with that choice open.
 */
export function AddPhoneReport({ caseId }: { caseId: string }) {
  return (
    <section aria-label="Add a phone report" className="flex max-w-3xl flex-col gap-2 rounded-lg border border-border bg-card p-4 text-sm">
      <h2 className="font-semibold">This case has no phone yet</h2>
      <p>
        A phone report is the export a phone extraction tool makes of a phone: its messages, calls, contacts, locations,
        photos and other records. Once a report is added, this section shows each phone, its conversations, patterns,
        money mentioned on it, and what still needs a person to decide.
      </p>
      <h3 className="font-medium">What you can add</h3>
      <ul className="list-disc pl-5">
        <li>A Cellebrite report folder (the folder holding the report and its files), chosen as a folder.</li>
        <li>The same report as one ZIP file, or a Cellebrite .ufdr file.</li>
        <li>One file can be at most 8 GB. For a larger report, unpack it and add the folder instead.</li>
        <li>One upload can hold at most 64 GB.</li>
      </ul>
      <p className="text-muted-foreground">The whole report is read and checked against itself when it arrives; its progress shows in the job tray.</p>
      <div>
        <Button asChild size="sm">
          <Link to={`/cases/${encodeURIComponent(caseId)}/evidence?add=phone`}>
            <Smartphone className="size-3.5" />
            Add a phone report
          </Link>
        </Button>
      </div>
    </section>
  )
}
