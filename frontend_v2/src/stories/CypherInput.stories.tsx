import type { Meta, StoryObj } from "@storybook/react-vite"
import { fn } from "@storybook/test"
import { CypherInput } from "@/components/ui/cypher-input"

const meta = {
  title: "@owl/ui/CypherInput",
  component: CypherInput,
  tags: ["autodocs"],
} satisfies Meta<typeof CypherInput>

export default meta
type Story = StoryObj<typeof meta>

export const Default: Story = {
  args: {
    placeholder: "MATCH (n) RETURN n",
    onExecute: fn(),
  },
}

export const WithValue: Story = {
  args: {
    defaultValue: "MATCH (p:Person)-[:KNOWS]->(o) RETURN p, o LIMIT 25",
    onExecute: fn(),
  },
}

export const Disabled: Story = {
  args: {
    placeholder: "MATCH (n) RETURN n",
    disabled: true,
  },
}
