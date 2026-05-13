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
  cell_tower: 'Cell tower',
  contact: 'Contact',
  app_session: 'App session',
  device_event: 'Device event',
  event: 'Event',
  generic: 'Item',
};

export function labelFor(type) {
  return TYPE_LABELS[type] || 'Item';
}
