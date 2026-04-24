/**
 * Helpers that each view uses to turn its local filter/selection state into a
 * compact payload ready for ChatContext.publish(...). Keep each row in
 * resultPreview to ~30 tokens or less so the backend prompt stays bounded.
 */

import { MAX_RESULT_IDS, MAX_RESULT_PREVIEW } from '../contexts/ChatContext';

const fmtDateOnly = (iso) => {
  if (!iso) return null;
  const s = String(iso);
  return s.length >= 10 ? s.slice(0, 10) : s;
};

const firstTruthy = (...vals) => vals.find((v) => v !== undefined && v !== null && v !== '');

const asList = (setOrArr) => {
  if (!setOrArr) return [];
  if (setOrArr instanceof Set) return [...setOrArr];
  if (Array.isArray(setOrArr)) return [...setOrArr];
  return [];
};

/**
 * Build view_context payload for the Financial view.
 */
export function buildFinancialContext({
  filters = {},
  rows = [],
  selectedKeys = [],
}) {
  const f = {};
  const labels = {};
  const addList = (key, values, label) => {
    const list = asList(values);
    if (list.length > 0) {
      f[key] = list;
      labels[key] = label;
    }
  };

  addList('types', filters.types, 'Transaction types');
  addList('categories', filters.categories, 'Categories');
  addList('fromEntities', filters.fromEntities, 'From entities');
  addList('toEntities', filters.toEntities, 'To entities');
  addList('moneyFlowEntities', filters.moneyFlowEntities, 'Money flow entities');
  if (filters.startDate) {
    f.startDate = fmtDateOnly(filters.startDate);
    labels.startDate = 'Start date';
  }
  if (filters.endDate) {
    f.endDate = fmtDateOnly(filters.endDate);
    labels.endDate = 'End date';
  }
  if (filters.searchQuery && String(filters.searchQuery).trim()) {
    f.searchQuery = String(filters.searchQuery).trim();
    labels.searchQuery = 'Search';
  }

  const resultIds = rows.map((r) => r.key || r.id).filter(Boolean);
  const resultPreview = rows.slice(0, MAX_RESULT_PREVIEW).map((r) => ({
    id: r.key || r.id,
    date: firstTruthy(r.date, r.timestamp, r.transaction_date) || null,
    from: firstTruthy(r.from_entity_name, r.from_name, r.source_entity) || null,
    to: firstTruthy(r.to_entity_name, r.to_name, r.destination_entity) || null,
    amount: firstTruthy(r.amount_usd, r.amount) ?? null,
    category: r.category || null,
    description: (r.description || r.name || '').toString().slice(0, 80) || null,
  }));

  return {
    viewType: 'financial',
    viewLabel: 'Financial view',
    filters: f,
    filterLabels: labels,
    selectionIds: asList(selectedKeys),
    resultIds: resultIds.slice(0, MAX_RESULT_IDS),
    resultPreview,
    totalMatching: rows.length,
  };
}

/**
 * Build view_context payload for the Graph table view.
 */
export function buildGraphTableContext({
  selectedNodes = [],
  activeTable = null,
  totalRows = 0,
  visibleRows = [],
}) {
  const f = {};
  const labels = {};
  if (activeTable) {
    f.activeTable = activeTable;
    labels.activeTable = 'Active table';
  }

  const resultPreview = visibleRows.slice(0, MAX_RESULT_PREVIEW).map((r) => ({
    id: r.key || r.id,
    label: r.label || r.type || null,
    name: r.name || null,
  }));

  return {
    viewType: 'graph_table',
    viewLabel: activeTable ? `Graph table · ${activeTable}` : 'Graph table',
    filters: f,
    filterLabels: labels,
    selectionIds: selectedNodes.map((n) => n.key).filter(Boolean),
    resultIds: visibleRows.map((r) => r.key || r.id).filter(Boolean).slice(0, MAX_RESULT_IDS),
    resultPreview,
    totalMatching: totalRows || visibleRows.length,
  };
}

/**
 * Build view_context payload for the Cellebrite Comms Center.
 */
export function buildCommsContext({
  reports = [],
  selectedReportKeys = new Set(),
  fromKeys = new Set(),
  toKeys = new Set(),
  activeTypes = new Set(),
  activeApps = new Set(),
  startDate = '',
  endDate = '',
  searchQuery = '',
  threads = [],
  selectedThread = null,
}) {
  const f = {};
  const labels = {};

  const devices = asList(selectedReportKeys);
  if (devices.length > 0 && devices.length < reports.length) {
    f.devices = devices.map((k) => {
      const r = reports.find((x) => x.report_key === k);
      return r?.device_model || k;
    });
    labels.devices = 'Devices';
  }
  const froms = asList(fromKeys);
  if (froms.length > 0) {
    f.fromKeys = froms;
    labels.fromKeys = 'From';
  }
  const tos = asList(toKeys);
  if (tos.length > 0) {
    f.toKeys = tos;
    labels.toKeys = 'To';
  }
  const types = asList(activeTypes);
  if (types.length > 0 && types.length < 3) {
    f.types = types;
    labels.types = 'Comm types';
  }
  const apps = asList(activeApps);
  if (apps.length > 0) {
    f.apps = apps;
    labels.apps = 'Source apps';
  }
  if (startDate) { f.startDate = startDate; labels.startDate = 'Start date'; }
  if (endDate) { f.endDate = endDate; labels.endDate = 'End date'; }
  if (searchQuery && searchQuery.trim()) {
    f.searchQuery = searchQuery.trim();
    labels.searchQuery = 'Search';
  }
  if (selectedThread?.thread_id) {
    f.selectedThread = selectedThread.name || selectedThread.thread_id;
    labels.selectedThread = 'Selected thread';
  }

  const resultIds = threads.map((t) => t.thread_id).filter(Boolean);
  const resultPreview = threads.slice(0, MAX_RESULT_PREVIEW).map((t) => ({
    id: t.thread_id,
    type: t.thread_type,
    app: t.source_app,
    name: t.name,
    participants: (t.participants || [])
      .map((p) => p.name)
      .filter(Boolean)
      .slice(0, 3)
      .join(', '),
    last_activity: t.last_activity || null,
    message_count: t.message_count || 0,
  }));

  return {
    viewType: 'comms',
    viewLabel: 'Cellebrite Comms Center',
    filters: f,
    filterLabels: labels,
    selectionIds: selectedThread?.thread_id ? [selectedThread.thread_id] : [],
    resultIds: resultIds.slice(0, MAX_RESULT_IDS),
    resultPreview,
    totalMatching: threads.length,
  };
}

/**
 * Build view_context payload for the Cellebrite Events Center.
 */
export function buildEventsContext({
  reports = [],
  selectedReportKeys = new Set(),
  activeEventTypes = new Set(),
  onlyGeolocated = false,
  startDate = '',
  endDate = '',
  playheadTime = null,
  events = [],
  selectedEvent = null,
}) {
  const f = {};
  const labels = {};
  const devices = asList(selectedReportKeys);
  if (devices.length > 0 && devices.length < reports.length) {
    f.devices = devices.map((k) => {
      const r = reports.find((x) => x.report_key === k);
      return r?.device_model || k;
    });
    labels.devices = 'Devices';
  }
  const types = asList(activeEventTypes);
  if (types.length > 0) {
    f.eventTypes = types;
    labels.eventTypes = 'Event types';
  }
  if (onlyGeolocated) {
    f.onlyGeolocated = true;
    labels.onlyGeolocated = 'Only geolocated';
  }
  if (startDate) { f.startDate = startDate; labels.startDate = 'Start date'; }
  if (endDate) { f.endDate = endDate; labels.endDate = 'End date'; }
  if (playheadTime) {
    f.playheadTime = playheadTime instanceof Date ? playheadTime.toISOString() : playheadTime;
    labels.playheadTime = 'Playhead';
  }

  const resultPreview = events.slice(0, MAX_RESULT_PREVIEW).map((e) => ({
    id: e.id || e.node_key,
    type: e.event_type,
    ts: e.timestamp,
    label: e.label,
    lat: e.latitude ?? null,
    lon: e.longitude ?? null,
    summary: (e.summary || '').slice(0, 80) || null,
  }));

  return {
    viewType: 'events',
    viewLabel: 'Cellebrite Location & Events',
    filters: f,
    filterLabels: labels,
    selectionIds: selectedEvent ? [selectedEvent.id || selectedEvent.node_key] : [],
    resultIds: events.map((e) => e.id || e.node_key).filter(Boolean).slice(0, MAX_RESULT_IDS),
    resultPreview,
    totalMatching: events.length,
  };
}

/**
 * Build view_context payload for the Cellebrite Files Explorer.
 */
export function buildFilesContext({
  reports = [],
  selectedReportKeys = new Set(),
  groupBy = 'category',
  activeNode = null,
  searchQuery = '',
  onlyRelevant = false,
  files = [],
  totalMatching = 0,
  selectedIds = new Set(),
}) {
  const f = { groupBy };
  const labels = { groupBy: 'Group by' };
  const devices = asList(selectedReportKeys);
  if (devices.length > 0 && devices.length < reports.length) {
    f.devices = devices.map((k) => {
      const r = reports.find((x) => x.report_key === k);
      return r?.device_model || k;
    });
    labels.devices = 'Devices';
  }
  if (activeNode?.label && activeNode?.filter) {
    f.activeNode = activeNode.label;
    labels.activeNode = 'Tree node';
    Object.entries(activeNode.filter).forEach(([k, v]) => {
      if (v) {
        f[k] = v;
        labels[k] = k.replace(/_/g, ' ');
      }
    });
  }
  if (searchQuery && searchQuery.trim()) {
    f.searchQuery = searchQuery.trim();
    labels.searchQuery = 'Search';
  }
  if (onlyRelevant) {
    f.onlyRelevant = true;
    labels.onlyRelevant = 'Only relevant';
  }

  const resultPreview = files.slice(0, MAX_RESULT_PREVIEW).map((f_) => ({
    id: f_.id,
    filename: f_.original_filename,
    category: f_.cellebrite_category,
    size: f_.size,
    tags: (f_.tags || []).slice(0, 5),
    parent: f_.parent?.label || null,
    source_app: f_.parent?.source_app || null,
  }));

  return {
    viewType: 'files',
    viewLabel: 'Cellebrite Files Explorer',
    filters: f,
    filterLabels: labels,
    selectionIds: asList(selectedIds),
    resultIds: files.map((x) => x.id).filter(Boolean).slice(0, MAX_RESULT_IDS),
    resultPreview,
    totalMatching: totalMatching || files.length,
  };
}

/**
 * Build view_context payload for the workspace sidebar section focus.
 */
export function buildWorkspaceContext({
  selectedSection = null,
  caseName = null,
}) {
  const f = {};
  const labels = {};
  if (selectedSection) {
    f.section = selectedSection;
    labels.section = 'Focused section';
  }
  if (caseName) {
    f.case = caseName;
    labels.case = 'Case';
  }
  const humanSection = (selectedSection || '')
    .split('-')
    .map((p) => (p ? p[0].toUpperCase() + p.slice(1) : ''))
    .join(' ');
  return {
    viewType: 'workspace_section',
    viewLabel: humanSection ? `Workspace · ${humanSection}` : 'Workspace',
    filters: f,
    filterLabels: labels,
    selectionIds: [],
    resultIds: [],
    resultPreview: [],
    totalMatching: 0,
  };
}
