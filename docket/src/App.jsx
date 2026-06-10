import React, { useEffect, useState, useCallback } from 'react'
import { ClipboardList, Plus, LogOut, RefreshCw } from 'lucide-react'
import { api, getToken, getName, clearSession } from './api.js'
import Login from './components/Login.jsx'
import Board from './components/Board.jsx'
import TicketDetail from './components/TicketDetail.jsx'
import NewTicketModal from './components/NewTicketModal.jsx'

export default function App() {
  const [authed, setAuthed] = useState(!!getToken())
  const [name, setName] = useState(getName())
  const [meta, setMeta] = useState(null)
  const [tickets, setTickets] = useState([])
  const [statusMeta, setStatusMeta] = useState({})
  const [openId, setOpenId] = useState(null)
  const [showNew, setShowNew] = useState(false)
  const [err, setErr] = useState('')

  // Drop to login on any 401 from the API client.
  useEffect(() => {
    const onUnauth = () => { setAuthed(false); setName('') }
    window.addEventListener('docket-unauth', onUnauth)
    return () => window.removeEventListener('docket-unauth', onUnauth)
  }, [])

  const loadBoard = useCallback(async () => {
    try {
      const r = await api.board()
      setTickets(r.tickets)
      setStatusMeta(r.status_meta)
      setErr('')
    } catch (e) {
      setErr(e.message)
    }
  }, [])

  // Load vocabulary once, then poll the board for live movement.
  useEffect(() => {
    if (!authed) return
    let alive = true
    api.meta().then((m) => { if (alive) setMeta(m) }).catch((e) => setErr(e.message))
    loadBoard()
    const iv = setInterval(loadBoard, 4000)
    return () => { alive = false; clearInterval(iv) }
  }, [authed, loadBoard])

  if (!authed) {
    return <Login onAuthed={(n) => { setName(n); setAuthed(true) }} />
  }

  return (
    <div className="min-h-screen flex flex-col">
      <header className="bg-white border-b border-slate-200 px-4 py-2.5 flex items-center gap-3">
        <ClipboardList className="w-5 h-5 text-indigo-600" />
        <span className="font-semibold text-slate-800">Docket</span>
        <span className="text-xs text-slate-400 hidden sm:inline">From ask to merge — in the open.</span>
        <div className="ml-auto flex items-center gap-2">
          <button onClick={() => setShowNew(true)}
            className="flex items-center gap-1 px-3 py-1.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-sm font-medium">
            <Plus className="w-4 h-4" /> New ticket
          </button>
          <span className="text-sm text-slate-500 px-2">{name}</span>
          <button onClick={() => { clearSession(); setAuthed(false) }}
            className="text-slate-400 hover:text-slate-600" title="Sign out">
            <LogOut className="w-4 h-4" />
          </button>
        </div>
      </header>

      {err && (
        <div className="bg-red-50 text-red-700 text-sm px-4 py-1.5 flex items-center gap-2">
          <RefreshCw className="w-3.5 h-3.5" /> {err}
        </div>
      )}

      <main className="flex-1 overflow-hidden">
        {meta
          ? <Board tickets={tickets} statusMeta={statusMeta} onOpen={setOpenId} />
          : <div className="p-8 text-slate-400">Loading board…</div>}
      </main>

      {openId != null && meta && (
        <TicketDetail
          ticketId={openId} meta={meta}
          onClose={() => setOpenId(null)}
          onChanged={loadBoard}
        />
      )}

      {showNew && meta && (
        <NewTicketModal
          meta={meta}
          onClose={() => setShowNew(false)}
          onCreated={(t) => { setShowNew(false); loadBoard(); setOpenId(t.id) }}
        />
      )}
    </div>
  )
}
