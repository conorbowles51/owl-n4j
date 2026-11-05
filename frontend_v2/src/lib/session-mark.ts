/**
 * Whether this browser is signed in, and which sign-in it is. Not a credential: the sign-in itself is the httpOnly
 * cookie, which page scripts cannot read. A new value is written at each sign-in, so work begun under one sign-in can
 * tell when another has replaced it.
 */
const MARK = "loupeSession"
// Where a browser signed in by an earlier release held its token. Read once to carry the sign-in over, then removed.
const OLD_TOKEN = "authToken"

function storage(): Storage | null {
  try {
    return localStorage
  } catch {
    return null
  }
}

function newValue() {
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`
}

export function sessionMark(): string | null {
  const store = storage()
  if (!store) return null
  if (store.getItem(OLD_TOKEN) !== null) {
    store.removeItem(OLD_TOKEN)
    store.setItem(MARK, newValue())
  }
  return store.getItem(MARK)
}

export function markSignedIn() {
  const store = storage()
  store?.removeItem(OLD_TOKEN)
  store?.setItem(MARK, newValue())
}

export function clearSessionMark() {
  const store = storage()
  store?.removeItem(OLD_TOKEN)
  store?.removeItem(MARK)
}
