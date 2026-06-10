import React, { useState } from 'react'
import { X } from 'lucide-react'
import { api } from '../api.js'

// Raise a new ticket. Acceptance criteria is a first-class field on purpose:
// it's the quiet lever for "write better stories" — what 'done' looks like.
export default function NewTicketModal({ meta, onClose, onCreated }) {
  const [title, setTitle] = useState('')
  const [type, setType] = useState('feature')
  const [priority, setPriority] = useState(meta.default_priority || 'P2')
  const [description, setDescription] = useState('')
  const [acceptance, setAcceptance] = useState('')
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)

  async function submit(e) {
    e.preventDefault()
    setErr('')
    setBusy(true)
    try {
      const r = await api.create({
        title, type, priority,
        description, acceptance_criteria: acceptance,
      })
      onCreated(r.ticket)
    } catch (e) {
      setErr(e.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50 p-4" onClick={onClose}>
      <form
        onClick={(e) => e.stopPropagation()}
        onSubmit={submit}
        className="w-full max-w-lg bg-white rounded-xl shadow-lg p-6"
      >
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-slate-800">New ticket</h2>
          <button type="button" onClick={onClose} className="text-slate-400 hover:text-slate-600">
            <X className="w-5 h-5" />
          </button>
        </div>

        <label className="block text-xs font-medium text-slate-600 mb-1">Title</label>
        <input
          className="w-full mb-3 px-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
          value={title} onChange={(e) => setTitle(e.target.value)} autoFocus
          placeholder="Short summary of the ask"
        />

        <div className="flex gap-3 mb-3">
          <div className="flex-1">
            <label className="block text-xs font-medium text-slate-600 mb-1">Type</label>
            <select className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm bg-white"
              value={type} onChange={(e) => setType(e.target.value)}>
              {meta.types.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
          </div>
          <div className="flex-1">
            <label className="block text-xs font-medium text-slate-600 mb-1">Priority</label>
            <select className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm bg-white"
              value={priority} onChange={(e) => setPriority(e.target.value)}>
              {meta.priorities.map((p) => <option key={p} value={p}>{p}</option>)}
            </select>
          </div>
        </div>

        <label className="block text-xs font-medium text-slate-600 mb-1">Description</label>
        <textarea
          className="w-full mb-3 px-3 py-2 border border-slate-300 rounded-lg text-sm h-24 focus:outline-none focus:ring-2 focus:ring-indigo-300"
          value={description} onChange={(e) => setDescription(e.target.value)}
          placeholder="What's the problem / ask? Why does it matter?"
        />

        <label className="block text-xs font-medium text-slate-600 mb-1">
          Acceptance criteria <span className="text-slate-400">— what does “done” look like?</span>
        </label>
        <textarea
          className="w-full mb-4 px-3 py-2 border border-slate-300 rounded-lg text-sm h-20 focus:outline-none focus:ring-2 focus:ring-indigo-300"
          value={acceptance} onChange={(e) => setAcceptance(e.target.value)}
          placeholder="e.g. The PDF prints full-width with no clipping on A4 and Letter"
        />

        {err && <div className="mb-3 text-sm text-red-600">{err}</div>}
        <div className="flex justify-end gap-2">
          <button type="button" onClick={onClose} className="px-4 py-2 text-sm text-slate-600 hover:text-slate-800">
            Cancel
          </button>
          <button type="submit" disabled={busy || !title.trim()}
            className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white rounded-lg text-sm font-medium">
            {busy ? 'Creating…' : 'Create ticket'}
          </button>
        </div>
      </form>
    </div>
  )
}
