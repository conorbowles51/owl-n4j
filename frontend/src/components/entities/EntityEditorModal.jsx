import React, { useEffect, useState } from 'react';
import { X, Save, Loader2 } from 'lucide-react';
import { entitiesAPI } from '../../services/api';
import { ENTITY_TYPES, entityMeta, entityColorClasses } from './entityUtils';

/**
 * Create or edit a CaseEntity.
 *
 * Props:
 *   caseId
 *   entity           — if present → edit mode
 *   defaultType      — type to preselect when creating
 *   onClose
 *   onSaved(entity)
 */
export default function EntityEditorModal({
  caseId,
  entity,
  defaultType = 'person',
  onClose,
  onSaved,
}) {
  const isEdit = !!entity?.id;
  const [form, setForm] = useState(() => ({
    entity_type: entity?.entity_type || defaultType,
    name: entity?.name || '',
    description: entity?.description || '',
    notes: entity?.notes || '',
    aliases: (entity?.aliases || []).join(', '),
    tags: (entity?.tags || []).join(', '),
    phone_numbers: (entity?.phone_numbers || []).join(', '),
    emails: (entity?.emails || []).join(', '),
    address: entity?.address || '',
    coordinates_lat: entity?.coordinates_lat ?? '',
    coordinates_lon: entity?.coordinates_lon ?? '',
    date: entity?.date || '',
    device_model: entity?.device_model || '',
    imei: entity?.imei || '',
    registration: entity?.registration || '',
    vehicle_make: entity?.vehicle_make || '',
    vehicle_model: entity?.vehicle_model || '',
    vehicle_color: entity?.vehicle_color || '',
    role: entity?.role || '',
    date_of_birth: entity?.date_of_birth || '',
  }));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  const csvToList = (csv) =>
    (csv || '')
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!form.name.trim()) {
      setError('Name is required');
      return;
    }
    setSaving(true);
    setError(null);
    const payload = {
      entity_type: form.entity_type,
      name: form.name.trim(),
      description: form.description || undefined,
      notes: form.notes || undefined,
      aliases: csvToList(form.aliases),
      tags: csvToList(form.tags),
      phone_numbers: csvToList(form.phone_numbers),
      emails: csvToList(form.emails),
      address: form.address || undefined,
      coordinates_lat: form.coordinates_lat !== '' ? Number(form.coordinates_lat) : undefined,
      coordinates_lon: form.coordinates_lon !== '' ? Number(form.coordinates_lon) : undefined,
      date: form.date || undefined,
      device_model: form.device_model || undefined,
      imei: form.imei || undefined,
      registration: form.registration || undefined,
      vehicle_make: form.vehicle_make || undefined,
      vehicle_model: form.vehicle_model || undefined,
      vehicle_color: form.vehicle_color || undefined,
      role: form.role || undefined,
      date_of_birth: form.date_of_birth || undefined,
    };
    try {
      let result;
      if (isEdit) {
        result = await entitiesAPI.update(caseId, entity.id, payload);
      } else {
        result = await entitiesAPI.create(caseId, payload);
      }
      onSaved?.(result);
      onClose?.();
    } catch (err) {
      setError(err.message || 'Failed to save entity');
    } finally {
      setSaving(false);
    }
  };

  const typeMeta = entityMeta(form.entity_type);
  const cls = entityColorClasses(form.entity_type);

  return (
    <div className="fixed inset-0 bg-black/30 z-50 flex items-center justify-center p-4">
      <form
        onSubmit={handleSubmit}
        className="bg-white rounded-lg shadow-xl w-full max-w-2xl max-h-[85vh] overflow-hidden flex flex-col"
      >
        <div className={`flex items-center justify-between p-4 border-b ${cls.bgSoft}`}>
          <h2 className={`text-base font-semibold ${cls.text}`}>
            {isEdit ? 'Edit Entity' : 'New Entity'}
          </h2>
          <button type="button" onClick={onClose} className="text-light-500 hover:text-light-800">
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-4 space-y-3">
          {/* Type selector */}
          <div>
            <label className="text-xs font-medium text-light-700">Type</label>
            <div className="flex flex-wrap gap-1 mt-1">
              {ENTITY_TYPES.map((t) => {
                const active = form.entity_type === t.key;
                const tcls = entityColorClasses(t.key);
                const Icon = t.icon;
                return (
                  <button
                    type="button"
                    key={t.key}
                    onClick={() => set('entity_type', t.key)}
                    className={`flex items-center gap-1 px-2 py-1 rounded-full border text-xs ${
                      active ? tcls.pill : 'bg-white border-light-300 text-light-600'
                    }`}
                  >
                    <Icon className="w-3 h-3" />
                    {t.label}
                  </button>
                );
              })}
            </div>
          </div>

          <Field label="Name *" required>
            <input
              type="text"
              value={form.name}
              onChange={(e) => set('name', e.target.value)}
              className="w-full px-2 py-1 text-sm border border-light-300 rounded focus:outline-none focus:border-owl-blue-400"
              autoFocus
              required
            />
          </Field>

          <Field label="Description">
            <input
              type="text"
              value={form.description}
              onChange={(e) => set('description', e.target.value)}
              className="w-full px-2 py-1 text-sm border border-light-300 rounded"
            />
          </Field>

          <Field label="Notes">
            <textarea
              value={form.notes}
              onChange={(e) => set('notes', e.target.value)}
              rows={3}
              className="w-full px-2 py-1 text-sm border border-light-300 rounded"
            />
          </Field>

          <div className="grid grid-cols-2 gap-2">
            <Field label="Aliases (comma-separated)">
              <input
                type="text"
                value={form.aliases}
                onChange={(e) => set('aliases', e.target.value)}
                className="w-full px-2 py-1 text-sm border border-light-300 rounded"
              />
            </Field>
            <Field label="Tags (comma-separated)">
              <input
                type="text"
                value={form.tags}
                onChange={(e) => set('tags', e.target.value)}
                className="w-full px-2 py-1 text-sm border border-light-300 rounded"
              />
            </Field>
          </div>

          {/* Type-specific fields */}
          {form.entity_type === 'person' && (
            <>
              <div className="grid grid-cols-2 gap-2">
                <Field label="Role">
                  <input
                    type="text"
                    value={form.role}
                    onChange={(e) => set('role', e.target.value)}
                    className="w-full px-2 py-1 text-sm border border-light-300 rounded"
                  />
                </Field>
                <Field label="Date of birth">
                  <input
                    type="date"
                    value={form.date_of_birth}
                    onChange={(e) => set('date_of_birth', e.target.value)}
                    className="w-full px-2 py-1 text-sm border border-light-300 rounded"
                  />
                </Field>
              </div>
              <Field label="Phone numbers (comma-separated)">
                <input
                  type="text"
                  value={form.phone_numbers}
                  onChange={(e) => set('phone_numbers', e.target.value)}
                  className="w-full px-2 py-1 text-sm border border-light-300 rounded"
                />
              </Field>
              <Field label="Emails (comma-separated)">
                <input
                  type="text"
                  value={form.emails}
                  onChange={(e) => set('emails', e.target.value)}
                  className="w-full px-2 py-1 text-sm border border-light-300 rounded"
                />
              </Field>
            </>
          )}

          {(form.entity_type === 'address' || form.entity_type === 'organisation' || form.entity_type === 'event') && (
            <>
              <Field label="Address">
                <input
                  type="text"
                  value={form.address}
                  onChange={(e) => set('address', e.target.value)}
                  className="w-full px-2 py-1 text-sm border border-light-300 rounded"
                />
              </Field>
              <div className="grid grid-cols-2 gap-2">
                <Field label="Latitude">
                  <input
                    type="number"
                    step="any"
                    value={form.coordinates_lat}
                    onChange={(e) => set('coordinates_lat', e.target.value)}
                    className="w-full px-2 py-1 text-sm border border-light-300 rounded"
                  />
                </Field>
                <Field label="Longitude">
                  <input
                    type="number"
                    step="any"
                    value={form.coordinates_lon}
                    onChange={(e) => set('coordinates_lon', e.target.value)}
                    className="w-full px-2 py-1 text-sm border border-light-300 rounded"
                  />
                </Field>
              </div>
            </>
          )}

          {form.entity_type === 'event' && (
            <Field label="Date / time (ISO 8601)">
              <input
                type="text"
                placeholder="2022-11-14T14:30:00Z"
                value={form.date}
                onChange={(e) => set('date', e.target.value)}
                className="w-full px-2 py-1 text-sm border border-light-300 rounded"
              />
            </Field>
          )}

          {form.entity_type === 'device' && (
            <div className="grid grid-cols-2 gap-2">
              <Field label="Device model">
                <input
                  type="text"
                  value={form.device_model}
                  onChange={(e) => set('device_model', e.target.value)}
                  className="w-full px-2 py-1 text-sm border border-light-300 rounded"
                />
              </Field>
              <Field label="IMEI">
                <input
                  type="text"
                  value={form.imei}
                  onChange={(e) => set('imei', e.target.value)}
                  className="w-full px-2 py-1 text-sm border border-light-300 rounded"
                />
              </Field>
            </div>
          )}

          {form.entity_type === 'vehicle' && (
            <>
              <div className="grid grid-cols-3 gap-2">
                <Field label="Registration">
                  <input
                    type="text"
                    value={form.registration}
                    onChange={(e) => set('registration', e.target.value)}
                    className="w-full px-2 py-1 text-sm border border-light-300 rounded"
                  />
                </Field>
                <Field label="Make">
                  <input
                    type="text"
                    value={form.vehicle_make}
                    onChange={(e) => set('vehicle_make', e.target.value)}
                    className="w-full px-2 py-1 text-sm border border-light-300 rounded"
                  />
                </Field>
                <Field label="Model">
                  <input
                    type="text"
                    value={form.vehicle_model}
                    onChange={(e) => set('vehicle_model', e.target.value)}
                    className="w-full px-2 py-1 text-sm border border-light-300 rounded"
                  />
                </Field>
              </div>
              <Field label="Colour">
                <input
                  type="text"
                  value={form.vehicle_color}
                  onChange={(e) => set('vehicle_color', e.target.value)}
                  className="w-full px-2 py-1 text-sm border border-light-300 rounded"
                />
              </Field>
            </>
          )}

          {error && <div className="text-xs text-red-600 italic">{error}</div>}
        </div>

        <div className="flex items-center justify-end gap-2 p-3 border-t border-light-200 bg-light-50">
          <button
            type="button"
            onClick={onClose}
            className="px-3 py-1.5 text-sm text-light-700 hover:bg-light-100 rounded"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={saving || !form.name.trim()}
            className="flex items-center gap-1 px-3 py-1.5 text-sm text-white bg-owl-blue-600 hover:bg-owl-blue-700 disabled:opacity-50 rounded"
          >
            {saving ? <Loader2 className="w-3 h-3 animate-spin" /> : <Save className="w-3 h-3" />}
            {isEdit ? 'Save' : 'Create'}
          </button>
        </div>
      </form>
    </div>
  );
}

function Field({ label, children, required }) {
  return (
    <label className="block">
      <div className="text-[11px] font-medium text-light-700 mb-0.5">
        {label}
        {required && <span className="text-red-600">*</span>}
      </div>
      {children}
    </label>
  );
}
