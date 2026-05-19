import { useMemo, useState } from "react"
import {
  ArrowUpDown,
  ChevronRight,
  Search,
  Smartphone,
  Users,
} from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { Input } from "@/components/ui/input"
import { LoadingSpinner } from "@/components/ui/loading-spinner"
import { cn } from "@/lib/cn"

import type { CellebriteRecord, PhoneReport, RailSelection } from "../../types"
import { useCellebriteCommunicationNetwork } from "../../hooks/use-cellebrite"
import { compactNumber } from "../shared/cellebrite-format"
import { PhoneReportChip } from "../shared/PhoneReportChip"
import { SmallEmpty } from "../shared/SmallEmpty"
import { ContactFeedDrawer } from "./ContactFeedDrawer"
import {
  compareContacts,
  contactCallCount,
  contactDevices,
  contactEmailCount,
  contactKey,
  contactMessageCount,
  contactName,
  contactPhone,
  contactSearchText,
  contactTotal,
  type CommunicationSortDir,
  type CommunicationSortField,
} from "./communicationsUtils"

export function CommunicationsTab({
  active,
  caseId,
  reportKeys,
  reports,
  query,
  onSelect,
}: {
  active: boolean
  caseId: string
  reportKeys: string[] | null
  reports: PhoneReport[]
  query: string
  onSelect: (selection: RailSelection) => void
}) {
  const networkQuery = useCellebriteCommunicationNetwork(caseId, active)
  const [searchTerm, setSearchTerm] = useState("")
  const [sortField, setSortField] =
    useState<CommunicationSortField>("call_count")
  const [sortDir, setSortDir] = useState<CommunicationSortDir>("desc")
  const [highlightedKey, setHighlightedKey] = useState<string | null>(null)
  const [drillContact, setDrillContact] = useState<CellebriteRecord | null>(
    null
  )

  const contacts = useMemo(
    () =>
      (networkQuery.data?.contacts ??
        networkQuery.data?.persons ??
        []) as CellebriteRecord[],
    [networkQuery.data?.contacts, networkQuery.data?.persons]
  )
  const sharedContacts = useMemo(
    () => (networkQuery.data?.shared_contacts ?? []) as CellebriteRecord[],
    [networkQuery.data?.shared_contacts]
  )

  const filteredContacts = useMemo(() => {
    const localNeedle = searchTerm.trim().toLowerCase()
    const globalNeedle = query.trim().toLowerCase()
    return [...contacts]
      .filter((contact) => {
        const text = contactSearchText(contact)
        return (
          (!localNeedle || text.includes(localNeedle)) &&
          (!globalNeedle || text.includes(globalNeedle))
        )
      })
      .sort((a, b) => compareContacts(a, b, sortField, sortDir))
  }, [contacts, query, searchTerm, sortDir, sortField])

  const openContact = (contact: CellebriteRecord) => {
    const key = contactKey(contact)
    setHighlightedKey(key)
    setDrillContact(contact)
    onSelect({
      id: key,
      kind: "contact",
      title: contactName(contact),
      payload: contact,
    })
  }

  const toggleSort = (field: CommunicationSortField) => {
    if (sortField === field) {
      setSortDir((current) => (current === "desc" ? "asc" : "desc"))
    } else {
      setSortField(field)
      setSortDir("desc")
    }
  }

  if (networkQuery.isLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <LoadingSpinner size="lg" />
      </div>
    )
  }

  if (networkQuery.isError) {
    return (
      <div className="flex h-full items-center justify-center">
        <SmallEmpty label="Could not load communication network" />
      </div>
    )
  }

  return (
    <>
      <section className="flex h-full min-h-0 overflow-hidden">
        <div className="flex min-w-0 flex-1 flex-col border-r border-border">
          <div className="flex shrink-0 items-center gap-2 border-b border-border bg-card px-4 py-2">
            <div className="relative min-w-[260px] flex-1">
              <Search className="absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
              <Input
                value={searchTerm}
                onChange={(event) => setSearchTerm(event.target.value)}
                placeholder="Search contacts..."
                className="h-8 pl-8 text-xs"
              />
            </div>
            <Badge variant="slate" className="shrink-0">
              {compactNumber(filteredContacts.length)} contacts
            </Badge>
          </div>

          <div className="min-h-0 flex-1 overflow-auto">
            <table className="w-full text-xs">
              <thead className="sticky top-0 z-10 bg-muted/70 backdrop-blur">
                <tr className="border-b border-border">
                  <th className="px-3 py-2 text-left font-semibold text-muted-foreground">
                    Name
                  </th>
                  <th className="px-3 py-2 text-left font-semibold text-muted-foreground">
                    Phone
                  </th>
                  <SortHeader
                    field="call_count"
                    label="Calls"
                    sortField={sortField}
                    sortDir={sortDir}
                    onSort={toggleSort}
                  />
                  <SortHeader
                    field="message_count"
                    label="Messages"
                    sortField={sortField}
                    sortDir={sortDir}
                    onSort={toggleSort}
                  />
                  <SortHeader
                    field="email_count"
                    label="Emails"
                    sortField={sortField}
                    sortDir={sortDir}
                    onSort={toggleSort}
                  />
                  <th className="px-3 py-2 text-center font-semibold text-muted-foreground">
                    Devices
                  </th>
                </tr>
              </thead>
              <tbody>
                {filteredContacts.map((contact) => {
                  const key = contactKey(contact)
                  const highlighted = highlightedKey === key
                  return (
                    <tr
                      key={key}
                      className={cn(
                        "group cursor-pointer border-b border-border/60 transition-colors",
                        highlighted ? "bg-amber-500/10" : "hover:bg-muted/50"
                      )}
                      onClick={() => openContact(contact)}
                      title="Click to see all calls, messages and emails"
                    >
                      <td className="max-w-[180px] truncate px-3 py-2 font-semibold text-foreground">
                        {contactName(contact)}
                      </td>
                      <td className="max-w-[140px] truncate px-3 py-2 font-mono text-[11px] text-muted-foreground">
                        {contactPhone(contact) || "-"}
                      </td>
                      <CountCell
                        value={contactCallCount(contact)}
                        variant="call"
                      />
                      <CountCell
                        value={contactMessageCount(contact)}
                        variant="message"
                      />
                      <CountCell
                        value={contactEmailCount(contact)}
                        variant="email"
                      />
                      <td className="px-3 py-2 text-center">
                        <span className="inline-flex items-center gap-1 text-muted-foreground">
                          <span>
                            {compactNumber(contactDevices(contact).length)}
                          </span>
                          <ChevronRight className="size-3 text-muted-foreground/60 transition-colors group-hover:text-amber-500" />
                        </span>
                      </td>
                    </tr>
                  )
                })}
                {filteredContacts.length === 0 && (
                  <tr>
                    <td
                      colSpan={6}
                      className="px-3 py-10 text-center text-muted-foreground"
                    >
                      No contacts found
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        <aside className="flex w-80 shrink-0 flex-col bg-muted/30">
          <div className="shrink-0 border-b border-border bg-card px-4 py-2.5">
            <div className="flex items-center gap-2">
              <Users className="size-4 text-amber-500" />
              <h3 className="text-sm font-semibold">Shared Contacts</h3>
              <Badge variant="amber" className="ml-auto">
                {compactNumber(sharedContacts.length)}
              </Badge>
            </div>
            <p className="mt-0.5 text-[10px] text-muted-foreground">
              Contacts appearing on multiple devices
            </p>
          </div>

          <div className="min-h-0 flex-1 space-y-2 overflow-y-auto p-3">
            {sharedContacts.length === 0 ? (
              <div className="flex h-full items-center justify-center px-4 text-center text-xs text-muted-foreground">
                {contacts.length > 0
                  ? "Contacts only appear on one device."
                  : "No shared contacts found."}
              </div>
            ) : (
              sharedContacts.map((contact) => {
                const key = contactKey(contact)
                const devices = contactDevices(contact)
                return (
                  <button
                    key={key}
                    type="button"
                    onClick={() => {
                      const fullContact =
                        contacts.find((item) => contactKey(item) === key) ??
                        contact
                      openContact(fullContact)
                    }}
                    className={cn(
                      "w-full rounded-md border bg-card p-2.5 text-left transition-colors",
                      highlightedKey === key
                        ? "border-amber-400 shadow-sm"
                        : "border-border hover:border-slate-300"
                    )}
                    title="Click to see all calls, messages and emails"
                  >
                    <div className="flex items-center gap-2">
                      <div className="flex size-7 shrink-0 items-center justify-center rounded-full bg-amber-500/15">
                        <Users className="size-3.5 text-amber-500" />
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="truncate text-xs font-semibold">
                          {contactName(contact)}
                        </div>
                        {contactPhone(contact) && (
                          <div className="truncate font-mono text-[10px] text-muted-foreground">
                            {contactPhone(contact)}
                          </div>
                        )}
                      </div>
                      {contactTotal(contact) > 0 && (
                        <Badge
                          variant="slate"
                          className="rounded-md text-[10px]"
                        >
                          {compactNumber(contactTotal(contact))}
                        </Badge>
                      )}
                    </div>
                    <div className="mt-2 flex flex-wrap gap-1">
                      {devices.length > 0 ? (
                        devices.map((key) => (
                          <PhoneReportChip
                            key={key}
                            reportKey={key}
                            reports={reports}
                            compact
                          />
                        ))
                      ) : (
                        <span className="inline-flex items-center gap-1 rounded-md bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground">
                          <Smartphone className="size-3" />
                          Device unknown
                        </span>
                      )}
                    </div>
                  </button>
                )
              })
            )}
          </div>
        </aside>
      </section>

      {drillContact && (
        <ContactFeedDrawer
          caseId={caseId}
          contact={drillContact}
          reportKeys={reportKeys}
          reports={reports}
          onClose={() => setDrillContact(null)}
          onSelect={onSelect}
        />
      )}
    </>
  )
}

function SortHeader({
  field,
  label,
  sortField,
  sortDir,
  onSort,
}: {
  field: CommunicationSortField
  label: string
  sortField: CommunicationSortField
  sortDir: CommunicationSortDir
  onSort: (field: CommunicationSortField) => void
}) {
  const active = sortField === field
  return (
    <th className="px-3 py-2 text-center font-semibold text-muted-foreground">
      <button
        type="button"
        onClick={() => onSort(field)}
        className="inline-flex items-center gap-1 rounded px-1 py-0.5 transition-colors hover:bg-muted hover:text-foreground"
      >
        {label}
        <ArrowUpDown
          className={cn(
            "size-3",
            active ? "text-amber-500" : "text-muted-foreground/50"
          )}
        />
        {active && <span className="sr-only">sorted {sortDir}</span>}
      </button>
    </th>
  )
}

function CountCell({
  value,
  variant,
}: {
  value: number
  variant: "call" | "message" | "email"
}) {
  const styles = {
    call: "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
    message: "bg-sky-500/10 text-sky-700 dark:text-sky-300",
    email: "bg-rose-500/10 text-rose-700 dark:text-rose-300",
  }
  return (
    <td className="px-3 py-2 text-center">
      {value > 0 ? (
        <span
          className={cn(
            "inline-flex min-w-7 justify-center rounded px-1.5 py-0.5 font-semibold",
            styles[variant]
          )}
        >
          {compactNumber(value)}
        </span>
      ) : (
        <span className="text-muted-foreground/40">-</span>
      )}
    </td>
  )
}
