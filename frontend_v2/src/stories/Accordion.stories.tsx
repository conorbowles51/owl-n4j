import type { Meta } from "@storybook/react-vite";
import {
  Accordion,
  AccordionItem,
  AccordionTrigger,
  AccordionContent,
} from "@/components/ui/accordion";

const meta = {
  title: "@owl/ui/Accordion",
  component: Accordion,
} satisfies Meta<typeof Accordion>;

export default meta;

export const Default = {
  render: () => (
    <Accordion type="single" collapsible className="w-[400px]">
      <AccordionItem value="item-1">
        <AccordionTrigger>What is OWL?</AccordionTrigger>
        <AccordionContent>
          OWL is an investigation console built on top of a Neo4j graph database
          for analyzing complex relationships.
        </AccordionContent>
      </AccordionItem>
      <AccordionItem value="item-2">
        <AccordionTrigger>How does case isolation work?</AccordionTrigger>
        <AccordionContent>
          All queries are filtered by case_id to ensure data isolation between
          different investigations.
        </AccordionContent>
      </AccordionItem>
      <AccordionItem value="item-3">
        <AccordionTrigger>What views are available?</AccordionTrigger>
        <AccordionContent>
          Graph, Timeline, Map, Table, and Financial views are currently
          supported.
        </AccordionContent>
      </AccordionItem>
    </Accordion>
  ),
};
