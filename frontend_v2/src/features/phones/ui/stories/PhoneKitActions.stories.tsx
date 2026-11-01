import type { Meta, StoryObj } from "@storybook/react-vite"
import { useEffect } from "react"
import { CopyButton } from "@/components/ui/copy-button"
import { register } from "@/lib/keymap"
import { KeymapOverlay } from "../KeymapOverlay"
import { ReportProblem } from "@/components/ui/report-problem"

/** Phone kit: copy helper, the keys overlay and Report a problem (07 sections 4.9, 4.10, 9). Light and dark. */
const meta = { title: "Phones/Kit/Actions", parameters: { layout: "padded" } } satisfies Meta
export default meta
type Story = StoryObj<typeof meta>

const Copy = () => (
  <div className="flex flex-col gap-3 bg-background p-4 text-foreground">
    <CopyButton rows={3} noun="messages" build={() => ({ text: "Avery Ashdown (+12015550100) → Blair Corwood (+13025550101)" })} />
    <CopyButton rows={12345} noun="messages" build={() => ({ text: "12,345 rows" })} label="Copy all 12,345" />
  </div>
)

const Keys = () => {
  useEffect(
    () =>
      register("Needs a decision", [
        { key: "y", label: "Looks right", run: () => {} },
        { key: "x", label: "Not right", run: () => {} },
        { key: "s", label: "Skip", run: () => {} },
        { key: "j", label: "Next reading", run: () => {} },
        { key: "c d", label: "Add to a dossier", run: () => {} },
      ]),
    []
  )
  return <KeymapOverlay open onOpenChange={() => {}} />
}

export const CopyLight: Story = { render: Copy, parameters: { theme: "light" } }
export const CopyDark: Story = { render: Copy, parameters: { theme: "dark" } }
export const KeysLight: Story = { render: Keys, parameters: { theme: "light" } }
export const KeysDark: Story = { render: Keys, parameters: { theme: "dark" } }

const Report = () => (
  <ReportProblem
    defaultOpen
    caseId="6587637c-0dff-45fa-8852-a6e4f7131c0c"
    screen="conversations"
    scope={{ messages: 2140, phones: 2 }}
    components={["scope-bar", "phone-table"]}
    send={async () => ({ id: "00000000-0000-4000-8000-000000000000", reference: "00000000" })}
  />
)
export const ReportLight: Story = { render: Report, parameters: { theme: "light" } }
export const ReportDark: Story = { render: Report, parameters: { theme: "dark" } }
