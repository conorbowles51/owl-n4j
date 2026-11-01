import type { Meta, StoryObj } from "@storybook/react-vite"
import { BadgeRow, OriginMark } from "../OriginMark"
import { PhoneChip } from "../PhoneChip"
import { ResultCount } from "../ResultCount"

/** Phone kit: count, origin marks, badges and phone chips (07 sections 4.5, 4.6, 4.8). Light and dark. */
const meta = { title: "Phones/Kit/Display", parameters: { layout: "padded" } } satisfies Meta
export default meta
type Story = StoryObj<typeof meta>

const Counts = () => (
  <div className="flex flex-col gap-2 bg-background p-4 text-foreground">
    <ResultCount shown={186787} total={186787} noun="messages" />
    <ResultCount shown={1204} total={1260} noun="positioned records" reason="56 cannot be placed" rest={<a className="underline" href="#why">Why</a>} />
    <ResultCount shown={2140} total={2140} noun="messages" unconfirmed={412} />
    <ResultCount shown={98000} total={186787} noun="messages" soFar />
  </div>
)

const Origins = () => (
  <div className="flex flex-col items-start gap-2 bg-background p-4 text-foreground">
    <OriginMark origin={{ state: "unconfirmed", rule: "The From field is read as the sender." }} onRule={() => {}} />
    <OriginMark origin={{ state: "machine", model: "Speech model", version: "1.0", on: "4 March 2024" }} />
    <OriginMark origin={{ state: "confirmed", by: "Sam Reviewer", on: "4 March 2024" }} />
    <OriginMark origin={{ state: "accepted", model: "the agent", by: "Sam Reviewer", on: "4 March 2024" }} />
    <OriginMark origin={{ state: "corrected", by: "Sam Reviewer", on: "4 March 2024", reason: "the sender is the other party", original: "Avery Ashdown" }} />
    <BadgeRow badges={["deleted", "unconfirmed", "duplicate", "synced"]} />
    <BadgeRow badges={["carved"]} />
  </div>
)

const Chips = () => (
  <div className="flex flex-wrap gap-2 bg-background p-4 text-foreground">
    {Array.from({ length: 10 }, (_, i) => (
      <PhoneChip key={i} label={`C${i + 1}`} index={i} />
    ))}
    <PhoneChip label="C1" index={0} extractionDate="2024-05-03" collides />
    <PhoneChip label="C1" index={10} extractionDate="2024-06-01" collides onRemove={() => {}} />
  </div>
)

export const CountLight: Story = { render: Counts, parameters: { theme: "light" } }
export const CountDark: Story = { render: Counts, parameters: { theme: "dark" } }
export const OriginLight: Story = { render: Origins, parameters: { theme: "light" } }
export const OriginDark: Story = { render: Origins, parameters: { theme: "dark" } }
export const ChipsLight: Story = { render: Chips, parameters: { theme: "light" } }
export const ChipsDark: Story = { render: Chips, parameters: { theme: "dark" } }
