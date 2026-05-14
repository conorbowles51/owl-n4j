/**
 * Registry of type-specific accordion renderers for the Cellebrite
 * right-rail. Looking up an unknown type falls back to GenericAccordion
 * so the rail never goes blank.
 *
 * Adding a new type: drop a new <Type>Accordion.jsx in this folder and
 * map it here. The component receives `{ selection }` and returns the
 * accordion body (the rail handles the title bar + collapse chrome).
 */

import GenericAccordion from './GenericAccordion';
import EventAccordion from './EventAccordion';
import LocationTileAccordion from './LocationTileAccordion';
import UnifiedContactAccordion from './UnifiedContactAccordion';

const RENDERERS = {
  // Event-like selections from the Events Center (any of the artifact
  // types it surfaces) all use one accordion that fetches detail and
  // delegates to the same projection logic as EventDetailDrawer.
  event:        EventAccordion,
  message:      EventAccordion,
  call:         EventAccordion,
  email:        EventAccordion,
  location:     EventAccordion,
  cell_tower:   EventAccordion,
  wifi:         EventAccordion,
  device_event: EventAccordion,
  app_session:  EventAccordion,
  // Aggregated location tile from the Locations tab — fetches the
  // rows inside the bucket and lets the user drill into any one of
  // them (clicking re-publishes as type 'location').
  location_tile: LocationTileAccordion,
  // Unified-by-number contact rolled up across all phones in the case
  // (Phase G). Payload is the full rollup row so no extra fetch.
  contact_unified: UnifiedContactAccordion,
};

export function rendererFor(type) {
  return RENDERERS[type] || GenericAccordion;
}

/**
 * Type → short label shown in the rail header.
 */
const TYPE_LABELS = {
  message: 'Message',
  call: 'Call',
  email: 'Email',
  location: 'Location',
  location_tile: 'Location tile',
  cell_tower: 'Cell tower',
  contact: 'Contact',
  contact_unified: 'Contact (unified)',
  app_session: 'App session',
  device_event: 'Device event',
  event: 'Event',
  generic: 'Item',
};

export function labelFor(type) {
  return TYPE_LABELS[type] || 'Item';
}
