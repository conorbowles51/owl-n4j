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

const RENDERERS = {
  // Filled in by B6b/c/d as we wire each tab. Until then every type
  // falls through to the generic key/value renderer.
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
