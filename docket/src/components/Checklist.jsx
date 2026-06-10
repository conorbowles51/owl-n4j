import React, { useEffect, useState, useCallback } from 'react'
import { Check, X as XIcon, Ban, ChevronRight, Plus } from 'lucide-react'
import { api, getName } from '../api.js'

// The migrated testing-hub checklist: a catalogue of shipped behaviours where
// each tester records pass / fail / blocked + a note per item. Distinct from the
// ticket pipeline — this is regression-style verification. A failing item can be
// turned straight into a Docket ticket via onRaiseTicket.

const VERDICTS = [
  { key: 'pass', label: 'Pass', icon: Check, on: 'bg-emerald-600 text-white border-emerald-600', off: 'text-emerald-700 border-emerald-300 hover:bg-emerald-50' },
  { key: 'fail', label: 'Fail', icon: XIcon, on: 'bg-rose-600 text-white border-rose-600', off: 'text-rose-700 border-rose-300 hover:bg-rose-50' },
  { key: 'blocked', label: 'Blocked', icon: Ban, on: 'bg-amber-500 text-white border-amber-500', off: 'text-amber-700 border-amber-300 hover:bg-amber-50' },
]
const DOT = { pass: 'bg-emerald-500', fail: 'bg-rose-500', blocked: 'bg-amber-500' }

export default function Checklist({ onRaiseTicket }) {
  const me = getName()
  const [sections, setSections] = useState([])
  const [feedback, setFeedback] = useState({})
  const [err, setErr] = useState('')
  const [open, setOpen] = useState({}) // section heading -> expanded

  const loadFeedback = useCallback(async () => {
    try { setFeedback((await api.feedback()).items || {}) }
    catch (e) { setErr(e.message) }
  }, [])

  useEffect(() => {
    api.checklist().then((d) => {
      setSections(d.sections || [])
      setOpen(Object.fromEntries((d.sections || []).map((s) => [s.h, true])))
    }).catch((e) => setErr(e.message))
    loadFeedback()
  }, [loadFeedback])

  async function setVerdict(itemId, status, currentNote) {
    try {
      await api.postFeedback(itemId, status, currentNote ?? null)
      await loadFeedback()
    } catch (e) { setErr(e.message) }
  }

  async function saveNote(itemId, note, currentStatus) {
    try {
      await api.postFeedback(itemId, currentStatus ?? null, note)
      await loadFeedback()
    } catch (e) { setErr(e.message) }
  }

  // counts for the per-section progress hint
  function sectionCount(sec) {
    let passed = 0
    for (const it of sec.items) {
      const byTester = feedback[it.id] || {}
      if (Object.values(byTester).some((r) => r.status === 'pass')) passed++
    }
    return { passed, total: sec.items.length }
  }

  return (
    <div className="max-w-4xl mx-auto p-4">
      {err && <div className="mb-3 text-sm text-red-600">{err}</div>}
      <p className="text-sm text-slate-500 mb-4">
        Verify each shipped behaviour and record <strong>pass / fail / blocked</strong>. Found a problem?
        Turn it straight into a ticket. Signed in as <strong>{me}</strong>.
      </p>

      {sections.map((sec) => {
        const { passed, total } = sectionCount(sec)
        const isOpen = open[sec.h]
        return (
          <div key={sec.h} className="mb-3 bg-white rounded-xl border border-slate-200 overflow-hidden">
            <button
              onClick={() => setOpen((o) => ({ ...o, [sec.h]: !o[sec.h] }))}
              className="w-full flex items-center gap-2 px-4 py-3 text-left hover:bg-slate-50"
            >
              <ChevronRight className={`w-4 h-4 text-slate-400 transition-transform ${isOpen ? 'rotate-90' : ''}`} />
              <span className="font-semibold text-slate-800">{sec.h}</span>
              <span className="ml-auto text-xs text-slate-400">{passed}/{total} passing</span>
            </button>

            {isOpen && (
              <div className="divide-y divide-slate-100">
                {sec.items.map((it) => {
                  const byTester = feedback[it.id] || {}
                  const mine = byTester[me] || {}
                  return (
                    <ChecklistItem
                      key={it.id} item={it} mine={mine} byTester={byTester}
                      onVerdict={(s) => setVerdict(it.id, s, mine.note)}
                      onNote={(n) => saveNote(it.id, n, mine.status)}
                      onRaiseTicket={() => onRaiseTicket({
                        title: it.t, type: 'bug',
                        description: `From checklist item "${it.id}".\n\nHow to test: ${it.how || ''}`,
                      })}
                    />
                  )
                })}
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}

function ChecklistItem({ item, mine, byTester, onVerdict, onNote, onRaiseTicket }) {
  const [note, setNote] = useState(mine.note || '')
  const [showHow, setShowHow] = useState(false)
  // keep local note in sync if feedback reloads
  useEffect(() => { setNote(mine.note || '') }, [mine.note])

  const others = Object.entries(byTester).filter(([, r]) => r.status)
  return (
    <div className="px-4 py-3">
      <div className="flex items-start gap-2">
        <div className="flex-1">
          <div className="text-sm text-slate-800 font-medium">{item.t}</div>
          <button onClick={() => setShowHow((v) => !v)} className="text-[11px] text-indigo-600 hover:underline mt-0.5">
            {showHow ? 'Hide how to test' : 'How to test'}
          </button>
          {showHow && <p className="text-xs text-slate-500 mt-1 whitespace-pre-wrap">{item.how}</p>}
        </div>
        {/* other testers' verdicts */}
        <div className="flex items-center gap-1">
          {others.map(([name, r]) => (
            <span key={name} title={`${name}: ${r.status}${r.note ? ' — ' + r.note : ''}`}
              className="flex items-center gap-0.5 text-[10px] text-slate-500">
              <span className={`w-2 h-2 rounded-full ${DOT[r.status] || 'bg-slate-300'}`} />
              {name[0]}
            </span>
          ))}
        </div>
      </div>

      <div className="flex items-center gap-2 mt-2 flex-wrap">
        {VERDICTS.map((v) => {
          const Icon = v.icon
          const active = mine.status === v.key
          return (
            <button key={v.key} onClick={() => onVerdict(active ? '' : v.key)}
              className={`flex items-center gap-1 px-2 py-1 text-xs rounded-lg border ${active ? v.on : v.off}`}>
              <Icon className="w-3 h-3" /> {v.label}
            </button>
          )
        })}
        <button onClick={onRaiseTicket}
          className="flex items-center gap-1 px-2 py-1 text-xs rounded-lg border border-slate-300 text-slate-600 hover:bg-slate-50 ml-auto">
          <Plus className="w-3 h-3" /> Raise ticket
        </button>
      </div>

      <input
        value={note}
        onChange={(e) => setNote(e.target.value)}
        onBlur={() => { if (note !== (mine.note || '')) onNote(note) }}
        placeholder="Add a note (optional)…"
        className="w-full mt-2 px-2 py-1 text-xs border border-slate-200 rounded focus:outline-none focus:ring-1 focus:ring-indigo-300"
      />
    </div>
  )
}
