import React, { useEffect, useState, useCallback } from 'react'
import {
  X, Bug, Sparkles, ArrowRight, Activity, ClipboardCheck,
  ListChecks, MessageSquare, StickyNote, ExternalLink, RefreshCw,
} from 'lucide-react'
import { api } from '../api.js'
import { PRIORITY_BADGE, KIND_DOT, relTime } from '../ui.js'

const KIND_ICON = {
  transition: ArrowRight,
  activity: Activity,
  assessment: ClipboardCheck,
  plan: ListChecks,
  comment: MessageSquare,
  note: StickyNote,
}

// Friendlier labels for the lifecycle buttons, keyed by "from->to".
const MOVE_LABEL = {
  'discussion->queued': 'Submit for processing',
  'pr->user_review': 'Approve → User Review',
  'pr->changes_requested': 'Request changes',
  'user_review->done': 'Pass — close ticket',
  'user_review->queued': 'Fail — amend & requeue',
  'user_review->discussion': 'Send back to discussion',
  'needs_info->queued': 'Info provided — requeue',
  'stalled->queued': 'Retry — requeue',
}

export default function TicketDetail({ ticketId, meta, onClose, onChanged }) {
  const [t, setT] = useState(null)
  const [comment, setComment] = useState('')
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    try {
      const r = await api.ticket(ticketId)
      setT(r.ticket)
    } catch (e) {
      setErr(e.message)
    }
  }, [ticketId])

  useEffect(() => {
    load()
    const iv = setInterval(load, 3000) // live timeline while open
    return () => clearInterval(iv)
  }, [load])

  async function move(to) {
    setBusy(true); setErr('')
    try {
      await api.transition(ticketId, to)
      await load(); onChanged && onChanged()
    } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }

  async function sendComment(e) {
    e.preventDefault()
    if (!comment.trim()) return
    setBusy(true); setErr('')
    try {
      await api.comment(ticketId, comment.trim())
      setComment(''); await load()
    } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }

  const meta_status = t ? (meta.status_meta[t.status] || {}) : {}
  const nextMoves = t ? (meta.transitions[t.status] || []) : []

  return (
    <div className="fixed inset-0 bg-black/30 flex justify-end z-40" onClick={onClose}>
      <div
        className="w-full max-w-xl bg-white h-full shadow-xl overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        {!t ? (
          <div className="p-8 text-slate-400">{err || 'Loading…'}</div>
        ) : (
          <>
            {/* Header */}
            <div className="sticky top-0 bg-white border-b border-slate-200 p-4 flex items-start gap-3">
              <div className="flex-1">
                <div className="flex items-center gap-2 mb-1">
                  <span className="font-mono text-xs text-slate-400">{t.ref}</span>
                  <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded ${PRIORITY_BADGE[t.priority]}`}>{t.priority}</span>
                  <span className="flex items-center gap-1 text-[11px] text-slate-500">
                    <span className={`w-2 h-2 rounded-full ${KIND_DOT[meta_status.kind] || 'bg-slate-400'}`} />
                    {meta_status.label || t.status}
                  </span>
                  {t.iteration > 0 && (
                    <span className="flex items-center gap-0.5 text-[11px] text-slate-500" title="re-submitted">
                      <RefreshCw className="w-3 h-3" />×{t.iteration}
                    </span>
                  )}
                </div>
                <div className="flex items-start gap-1.5">
                  {t.type === 'bug'
                    ? <Bug className="w-4 h-4 text-rose-500 mt-1 shrink-0" />
                    : <Sparkles className="w-4 h-4 text-indigo-500 mt-1 shrink-0" />}
                  <h2 className="text-lg font-semibold text-slate-800 leading-snug">{t.title}</h2>
                </div>
              </div>
              <button onClick={onClose} className="text-slate-400 hover:text-slate-600"><X className="w-5 h-5" /></button>
            </div>

            <div className="p-4 space-y-4">
              {err && <div className="text-sm text-red-600">{err}</div>}

              {/* Lifecycle actions */}
              {nextMoves.length > 0 && (
                <div className="flex flex-wrap gap-2">
                  {nextMoves.map((to) => (
                    <button key={to} disabled={busy} onClick={() => move(to)}
                      className="px-3 py-1.5 text-xs font-medium rounded-lg border border-indigo-300 text-indigo-700 hover:bg-indigo-50 disabled:opacity-50">
                      {MOVE_LABEL[`${t.status}->${to}`] || (meta.status_meta[to]?.label) || to}
                    </button>
                  ))}
                </div>
              )}

              {t.position != null && (
                <div className="text-sm text-amber-700 bg-amber-50 rounded-lg px-3 py-2">
                  In the queue — position #{t.position}.
                </div>
              )}

              {t.pr_url && (
                <a href={t.pr_url} target="_blank" rel="noreferrer"
                  className="inline-flex items-center gap-1 text-sm text-indigo-600 hover:underline">
                  <ExternalLink className="w-3.5 h-3.5" /> View PR
                </a>
              )}

              <Section title="Description" body={t.description} />
              <Section title="Acceptance criteria" body={t.acceptance_criteria} />
              {t.test_instructions && <Section title="How to test" body={t.test_instructions} />}

              {/* Timeline */}
              <div>
                <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">Timeline</h3>
                <div className="space-y-2">
                  {t.events.map((ev) => {
                    const Icon = KIND_ICON[ev.kind] || StickyNote
                    return (
                      <div key={ev.id} className="flex gap-2 text-sm">
                        <Icon className="w-3.5 h-3.5 text-slate-400 mt-0.5 shrink-0" />
                        <div className="flex-1">
                          <span className="text-slate-700">{ev.summary}</span>
                          <span className="ml-2 text-[11px] text-slate-400">
                            {ev.actor || 'system'} · {relTime(ev.ts)}
                          </span>
                        </div>
                      </div>
                    )
                  })}
                </div>
              </div>

              {/* Comment */}
              <form onSubmit={sendComment} className="pt-2">
                <textarea
                  className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm h-16 focus:outline-none focus:ring-2 focus:ring-indigo-300"
                  value={comment} onChange={(e) => setComment(e.target.value)}
                  placeholder="Add a comment…"
                />
                <div className="flex justify-end mt-2">
                  <button type="submit" disabled={busy || !comment.trim()}
                    className="px-3 py-1.5 bg-slate-800 hover:bg-slate-900 disabled:opacity-50 text-white rounded-lg text-xs font-medium">
                    Comment
                  </button>
                </div>
              </form>
            </div>
          </>
        )}
      </div>
    </div>
  )
}

function Section({ title, body }) {
  return (
    <div>
      <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1">{title}</h3>
      <p className="text-sm text-slate-700 whitespace-pre-wrap">{body || <span className="text-slate-400 italic">—</span>}</p>
    </div>
  )
}
