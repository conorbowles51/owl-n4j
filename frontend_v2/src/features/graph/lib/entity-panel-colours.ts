import { getNodeColor, nodeColors, type EntityType } from "@/lib/theme"

/**
 * Entity-type colours of the entity and relationship panel (GR-04), one named mapping from the existing palette.
 *
 * Before this the panel took each colour from the shared lookup, where 20 of the 33 types in the cases (measured
 * 9 Nov 2026) had no entry and got a palette colour picked by hashing the type name. Testers liked the result
 * ("distinguishes entity types at a glance"), so every type keeps the colour it showed then; it is now written down
 * here instead of falling out of a hash, and a test fails if an entry is lost or changed. A type not listed still
 * takes the shared lookup's colour, so a new type is never left uncoloured.
 */
export const ENTITY_PANEL_TYPE_COLOURS: Readonly<Record<string, EntityType>> = {
  person: "person",
  phoneidentity: "person",
  organization: "organization",
  company: "organization",
  financialtransaction: "organization",
  legalaction: "organization",
  location: "location",
  media: "location",
  transaction: "financial",
  account: "financial",
  bank: "financial",
  phoneextraction: "financial",
  document: "document",
  financialaccount: "document",
  financialinstrument: "document",
  physicalevidence: "document",
  drug: "document",
  ingestioncasewritelock: "document",
  event: "event",
  financialparty: "event",
  networkidentifier: "event",
  communication: "communication",
  other: "communication",
  weapon: "communication",
  vehicle: "vehicle",
  digitalaccount: "vehicle",
  group: "vehicle",
  device: "digital",
  financialstatementperiod: "evidence",
  phonegroup: "evidence",
  phonenumber: "evidence",
  cyberidentity: "evidence",
}

/** The panel colour for an entity type (case-insensitive). */
export function entityPanelColour(type: string): string {
  const named = ENTITY_PANEL_TYPE_COLOURS[(type ?? "").toLowerCase()]
  return named ? nodeColors[named] : getNodeColor(type)
}
