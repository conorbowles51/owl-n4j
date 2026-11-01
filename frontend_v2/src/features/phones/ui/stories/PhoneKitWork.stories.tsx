import type { Meta, StoryObj } from "@storybook/react-vite"
import { useState } from "react"
import { GuideDialog } from "@/components/ui/guide-dialog"
import { JobTray } from "@/components/ui/job-tray"
import { ProgressPanel } from "@/components/ui/progress-panel"
import { usePhoneSelection } from "@/stores/phone-selection.store"
import { CASE_ZONE, messageView, stripDays, TRAINING } from "../../fixtures"
import { AddToMenu } from "../AddToMenu"
import { DockedPanel } from "../DockedPanel"
import { PhoneTable } from "../PhoneTable"
import { RecordPanelContent } from "../RecordPanel"
import { EMPTY_SCOPE, ScopeBar, type Scope } from "../ScopeBar"
import { TimeStrip } from "../TimeStrip"

/** Phone kit: waiting, jobs, time strip, scope, table, record panel, Add to… and the guide, on synthetic phones. */
const meta = { title: "Phones/Kit/Work", parameters: { layout: "fullscreen" } } satisfies Meta
export default meta
type Story = StoryObj<typeof meta>

const wrap = (node: React.ReactNode) => <div className="flex flex-col gap-3 bg-background p-4 text-foreground">{node}</div>

const Progress = () =>
  wrap(
    <>
      <ProgressPanel progress={{ step: "Counting matching messages on 3 phones", done: 98000, total: 186787, unit: "messages", startedAt: 0, movedAt: 9000 }} now={10000} />
      <ProgressPanel progress={{ step: "Counting matching messages on 3 phones", done: 0, total: 186787, unit: "messages", startedAt: 0, movedAt: 0 }} now={1000} />
      <ProgressPanel progress={{ step: "Loading the thread", startedAt: 0, movedAt: 0 }} now={11000} onRetry={() => {}} />
      <ProgressPanel background progress={{ step: "Reading records", done: 12000, total: 71045, unit: "records", startedAt: 0, movedAt: 0 }} now={45000} formatClock={() => "3:04:05 PM"} />
      <JobTray
        defaultOpen
        now={10000}
        jobs={[
          { id: "1", title: "Getting C5 ready", state: "running", progress: { step: "Reading records", done: 12000, total: 71045, unit: "records", startedAt: 0, movedAt: 9000 }, href: "#", onCancel: () => {}, cancelWords: "files already checked are kept" },
          { id: "2", title: "Export: messages between two people", state: "done", progress: { step: "Drawing pages", startedAt: 0, movedAt: 0 }, href: "#" },
        ]}
      />
    </>
  )

const Strip = () => wrap(<TimeStrip days={stripDays(TRAINING, "C5")} zone="Eastern time (UTC-5)" onPickDay={() => {}} />)

const ScopeStory = () => {
  const [scope, setScope] = useState<Scope>({
    ...EMPTY_SCOPE,
    people: [{ key: TRAINING.people[0].key, label: TRAINING.people[0].name }, { key: TRAINING.people[1].key, label: TRAINING.people[1].name }],
    mode: "between",
    phones: TRAINING.phones.map((p, i) => ({ id: p.label, label: p.label, index: i, extractionDate: p.extraction_date })),
    window: { from: "1 Jan 2024", to: "31 Mar 2024" },
  })
  return wrap(
    <ScopeBar
      scope={scope}
      onChange={setScope}
      count={{ shown: 214, total: 214, noun: "messages and calls", unconfirmed: 214 }}
      presets={[{ label: `Phones of ${TRAINING.people[0].name}`, scope: { ...EMPTY_SCOPE, phones: [{ id: "C5", label: "C5", index: 0 }] } }]}
    />
  )
}

const Table = () => {
  const people = TRAINING.people.map((p) => ({ ...p, calls: TRAINING.calls.filter((c) => c.other === p.key).length }))
  return wrap(
    <PhoneTable
      rows={people}
      total={people.length}
      rowId={(r) => r.key}
      noun="people"
      label="People on the phones"
      height={260}
      columns={[
        { id: "name", header: "Name", width: 220, cell: (r) => r.name, sortValue: (r) => r.name },
        { id: "number", header: "Number", width: 160, cell: (r) => r.numbers[0], sortValue: (r) => r.numbers[0] },
        { id: "calls", header: "Calls", width: 90, cell: (r) => r.calls, sortValue: (r) => r.calls },
      ]}
    />
  )
}

const Record = () => {
  const view = { ...messageView(TRAINING, TRAINING.messages[3]), usedIn: { findings: 1, dossiers: 1, notes: 0, timeline: 0, labels: 0 } }
  return (
    <div className="flex h-[640px] bg-background text-foreground">
      <main className="flex-1 p-4">
        <p>The conversation stays here; j and k keep moving while the panel is open.</p>
      </main>
      <DockedPanel title="Record" open onClose={() => {}}>
        <RecordPanelContent record={{ ...view, zone: CASE_ZONE }} onAddTo={() => {}} onAround={() => {}} onWindow={() => {}} onCorrect={() => {}} />
      </DockedPanel>
    </div>
  )
}

const AddTo = () => {
  usePhoneSelection.getState().setCase("story")
  return wrap(
    <AddToMenu
      caseId="story"
      links={TRAINING.messages.slice(0, 12).map((m) => ({ target_type: "phone_record", target_id: m.id, source_anchor: {} }))}
      noun="messages"
      origin="Added from Conversations"
      client={{ add: async (_c, _t, part) => ({ added: part.length, skipped: 0, refused: 0 }) }}
      targets={[{ kind: "finding", id: "f1", label: "Meetings arranged by message", recent: true }, { kind: "dossier", id: "d1", label: TRAINING.people[1].name, linkedPerson: true }]}
      keys={false}
    />
  )
}

const Guide = () =>
  wrap(
    <GuideDialog
      defaultOpen
      guides={[{ id: "user", label: "User guide", title: "Phone user guide", url: "#", directory: "/", heading: "# Phone user guide", prefix: "pg" }]}
      preloaded={{ user: "# Phone user guide\n\n## Start with the Phone summary\n\nIt says what was read, the period covered and what needs a decision." }}
    />
  )

export const ProgressLight: Story = { render: Progress, parameters: { theme: "light" } }
export const ProgressDark: Story = { render: Progress, parameters: { theme: "dark" } }
export const StripLight: Story = { render: Strip, parameters: { theme: "light" } }
export const StripDark: Story = { render: Strip, parameters: { theme: "dark" } }
export const ScopeLight: Story = { render: ScopeStory, parameters: { theme: "light" } }
export const ScopeDark: Story = { render: ScopeStory, parameters: { theme: "dark" } }
export const TableLight: Story = { render: Table, parameters: { theme: "light" } }
export const TableDark: Story = { render: Table, parameters: { theme: "dark" } }
export const RecordLight: Story = { render: Record, parameters: { theme: "light" } }
export const RecordDark: Story = { render: Record, parameters: { theme: "dark" } }
export const AddToLight: Story = { render: AddTo, parameters: { theme: "light" } }
export const AddToDark: Story = { render: AddTo, parameters: { theme: "dark" } }
export const GuideLight: Story = { render: Guide, parameters: { theme: "light" } }
export const GuideDark: Story = { render: Guide, parameters: { theme: "dark" } }
