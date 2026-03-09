import type { Meta, StoryObj } from "@storybook/react-vite";
import {
  Command,
  CommandInput,
  CommandList,
  CommandEmpty,
  CommandGroup,
  CommandItem,
} from "@/components/ui/command";
import { Search } from "lucide-react";

const meta = {
  title: "@owl/ui/Command",
  component: Command,
} satisfies Meta<typeof Command>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  render: () => (
    <Command className="w-[350px] rounded-lg border">
      <CommandInput placeholder="Search entities..." />
      <CommandList>
        <CommandEmpty>No results found.</CommandEmpty>
        <CommandGroup heading="People">
          <CommandItem>
            <Search className="mr-2 h-4 w-4" />
            John Doe
          </CommandItem>
          <CommandItem>
            <Search className="mr-2 h-4 w-4" />
            Jane Smith
          </CommandItem>
        </CommandGroup>
        <CommandGroup heading="Organizations">
          <CommandItem>
            <Search className="mr-2 h-4 w-4" />
            Acme Corp
          </CommandItem>
          <CommandItem>
            <Search className="mr-2 h-4 w-4" />
            Globex Inc
          </CommandItem>
        </CommandGroup>
      </CommandList>
    </Command>
  ),
};
