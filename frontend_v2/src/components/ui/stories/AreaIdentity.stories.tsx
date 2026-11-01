import type { Meta, StoryObj } from "@storybook/react-vite"
import { Inbox } from "lucide-react"
import { AreaContext, ViewHeader } from "../view-header"
import { EmptyState } from "../empty-state"
import { AREA_IDS, CASE_VIEWS } from "@/lib/areas"

/** lx-style B and C: every case view's identity band, and an empty state in each area. Light and dark. */
const meta = { title: "Style/Area identity", parameters: { layout: "fullscreen" } } satisfies Meta
export default meta
type Story = StoryObj<typeof meta>

const Headers = () => (
  <main className="flex flex-col gap-2 bg-background p-4 text-foreground">
    {CASE_VIEWS.filter((v) => v.segment !== "profiles").map((v) => (
      <ViewHeader key={v.segment} view={v} />
    ))}
  </main>
)

const Empties = () => (
  <main className="grid grid-cols-4 gap-2 bg-background p-4 text-foreground">
    {AREA_IDS.map((area) => (
      <AreaContext.Provider key={area} value={area}>
        <EmptyState icon={Inbox} title={`Nothing here yet (${area})`} description="Add evidence to the case to see it here." />
      </AreaContext.Provider>
    ))}
  </main>
)

export const HeadersLight: Story = { render: Headers, parameters: { theme: "light" } }
export const HeadersDark: Story = { render: Headers, parameters: { theme: "dark" } }
export const EmptyLight: Story = { render: Empties, parameters: { theme: "light" } }
export const EmptyDark: Story = { render: Empties, parameters: { theme: "dark" } }
