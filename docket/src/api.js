// Docket API client. Reuses the testing-hub login (tester JWT) for auth: the
// token is stored in localStorage and sent as a Bearer header on every call.
// A 401 clears the token and fires a 'docket-unauth' event so the app drops
// back to the login screen.

const TOKEN_KEY = 'docket-token'
const NAME_KEY = 'docket-name'

export function getToken() { return localStorage.getItem(TOKEN_KEY) || '' }
export function getName() { return localStorage.getItem(NAME_KEY) || '' }
export function setSession(token, name) {
  localStorage.setItem(TOKEN_KEY, token)
  localStorage.setItem(NAME_KEY, name || '')
}
export function clearSession() {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(NAME_KEY)
}

async function req(path, opts = {}) {
  const headers = { 'Content-Type': 'application/json', ...(opts.headers || {}) }
  const t = getToken()
  if (t) headers['Authorization'] = `Bearer ${t}`
  const res = await fetch(path, { ...opts, headers })
  if (res.status === 401) {
    clearSession()
    window.dispatchEvent(new Event('docket-unauth'))
    throw new Error('Session expired — please sign in again')
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || 'Request failed')
  }
  return res.status === 204 ? null : res.json()
}

export const api = {
  login: (username, password) =>
    req('/api/testing/login', { method: 'POST', body: JSON.stringify({ username, password }) }),
  me: () => req('/api/testing/me'),

  meta: () => req('/api/tickets/meta'),
  testers: () => req('/api/tickets/testers'),
  board: () => req('/api/tickets/board'),
  ticket: (id) => req(`/api/tickets/${id}`),
  create: (body) => req('/api/tickets', { method: 'POST', body: JSON.stringify(body) }),
  patch: (id, body) => req(`/api/tickets/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
  submit: (id, body) => req(`/api/tickets/${id}/submit`, { method: 'POST', body: JSON.stringify(body || {}) }),
  transition: (id, to_status, summary) =>
    req(`/api/tickets/${id}/transition`, { method: 'POST', body: JSON.stringify({ to_status, summary: summary || '' }) }),
  resubmit: (id, body) =>
    req(`/api/tickets/${id}/resubmit`, { method: 'POST', body: JSON.stringify(body) }),
  comment: (id, text) =>
    req(`/api/tickets/${id}/comment`, { method: 'POST', body: JSON.stringify({ text }) }),

  // Migrated testing-hub checklist (per-tester pass/fail/blocked of shipped behaviours).
  checklist: () => req('/api/testing/checklist'),
  feedback: () => req('/api/testing/feedback'),
  postFeedback: (item_id, status, note) =>
    req('/api/testing/feedback', { method: 'POST', body: JSON.stringify({ item_id, status, note }) }),
}
