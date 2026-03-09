import type { Meta, StoryObj } from "@storybook/react-vite";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";

const meta = {
  title: "@owl/ui/ScrollArea",
  component: ScrollArea,
} satisfies Meta<typeof ScrollArea>;

export default meta;
type Story = StoryObj<typeof meta>;

const items = Array.from({ length: 30 }, (_, i) => `Entity ${i + 1}`);

export const Default: Story = {
  render: () => (
    <ScrollArea className="h-[200px] w-[250px] rounded-md border p-4">
      <div className="space-y-1">
        {items.map((item) => (
          <div key={item}>
            <p className="text-sm text-foreground">{item}</p>
            <Separator className="my-1" />
          </div>
        ))}
      </div>
    </ScrollArea>
  ),
};
