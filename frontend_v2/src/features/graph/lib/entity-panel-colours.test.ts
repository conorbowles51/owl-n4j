import { expect, it } from "vitest"
import { ENTITY_PANEL_TYPE_COLOURS, entityPanelColour } from "./entity-panel-colours"

// GR-04: the colours testers saw in the entity panel on 9 Nov 2026, one per entity type in the cases. A lost or
// changed entry fails here.
const SEEN = {
  Transaction: "#B37A2E", Event: "#C25778", Document: "#72757E", FinancialTransaction: "#8060A9",
  Communication: "#2C8197", Person: "#5571C8", Location: "#238A88", PhoneIdentity: "#5571C8", Account: "#B37A2E",
  Company: "#8060A9", LegalAction: "#8060A9", FinancialInstrument: "#72757E", FinancialAccount: "#72757E",
  Bank: "#B37A2E", FinancialStatementPeriod: "#C4653F", Other: "#2C8197", IngestionCaseWriteLock: "#72757E",
  Organization: "#8060A9", PhoneExtraction: "#B37A2E", PhoneGroup: "#C4653F", person: "#5571C8",
  FinancialParty: "#C25778", DigitalAccount: "#6F8B45", PhoneNumber: "#C4653F", PhysicalEvidence: "#72757E",
  Media: "#238A88", Device: "#765FA6", Group: "#6F8B45", Weapon: "#2C8197", Vehicle: "#6F8B45",
  NetworkIdentifier: "#C25778", CyberIdentity: "#C4653F", Drug: "#72757E",
} as const

it("keeps the colour each entity type showed in the panel, from one named mapping", () => {
  for (const [type, colour] of Object.entries(SEEN)) {
    expect([type, entityPanelColour(type)]).toEqual([type, colour])
    expect(ENTITY_PANEL_TYPE_COLOURS[type.toLowerCase()], type).toBeDefined()
  }
})

it("still colours a type it does not list", () => {
  expect(entityPanelColour("Spaceship")).toMatch(/^#[0-9A-F]{6}$/i)
})
