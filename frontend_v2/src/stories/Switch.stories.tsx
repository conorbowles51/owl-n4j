import type { Meta, StoryObj } from "@storybook/react-vite";
import { Switch } from "@/components/ui/switch";

const meta = {
  title: "@owl/ui/Switch",
  component: Switch,
} satisfies Meta<typeof Switch>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};

export const Checked: Story = {
  args: {
    defaultChecked: true,
  },
};

export const Disabled: Story = {
  args: {
    disabled: true,
  },
};

export const WithLabel: Story = {
  render: () => (
    <div className="flex items-center gap-2">
      <Switch id="notifications" />
      <label
        htmlFor="notifications"
        className="text-sm font-medium leading-none text-foreground"
      >
        Enable notifications
      </label>
    </div>
  ),
};
