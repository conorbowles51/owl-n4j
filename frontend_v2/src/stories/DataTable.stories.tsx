import type { Meta } from "@storybook/react-vite";
import { DataTable, type DataTableColumn } from "@/components/ui/data-table";

interface Person {
  id: string;
  name: string;
  role: string;
  status: string;
}

const columns: DataTableColumn<Person>[] = [
  {
    key: "name",
    header: "Name",
    cell: (row) => row.name,
  },
  {
    key: "role",
    header: "Role",
    cell: (row) => row.role,
  },
  {
    key: "status",
    header: "Status",
    cell: (row) => row.status,
  },
];

const data: Person[] = [
  { id: "1", name: "John Doe", role: "Analyst", status: "Active" },
  { id: "2", name: "Jane Smith", role: "Investigator", status: "Active" },
  { id: "3", name: "Bob Wilson", role: "Supervisor", status: "Inactive" },
  { id: "4", name: "Alice Brown", role: "Analyst", status: "Active" },
];

const meta = {
  title: "@owl/ui/DataTable",
  component: DataTable,
} satisfies Meta<typeof DataTable>;

export default meta;

export const Default = {
  render: () => (
    <DataTable
      columns={columns}
      data={data}
      getRowKey={(row) => row.id}
      emptyMessage="No people found"
    />
  ),
};
