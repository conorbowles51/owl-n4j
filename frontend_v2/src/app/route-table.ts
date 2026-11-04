import { createRoutesFromChildren, type RouteObject } from "react-router-dom"
import { useAuthStore } from "@/features/auth/hooks/use-auth"
import type { User } from "@/features/auth/auth.types"
import { queryClient } from "@/lib/query-client"
import { registerRouteTree, routeDataFor, routePageFor } from "@/lib/route-preload"
import { AppRoutes } from "./routes"

let tree: RouteObject[] | null = null

/** app/routes.tsx's <Route> tree as react-router route objects (read once; AppRoutes holds no hooks). */
export function appRouteTree(): RouteObject[] {
  if (!tree) tree = createRoutesFromChildren((AppRoutes() as { props: { children: React.ReactNode } }).props.children)
  return tree
}

/**
 * Calls `then` once with the signed-in person, as soon as the sign-in check (ProtectedRoute's /api/auth/me, sent
 * early by main.tsx: `signedIn`) has answered: requests that need the session wait for it exactly as the page's
 * own do. Never if the check fails or the person is signed out first.
 */
function whenSignedIn(signedIn: Promise<User> | null, then: (user: User) => void) {
  const now = useAuthStore.getState()
  if (now.user) return then(now.user)
  let done = false
  const once = (user: User) => {
    if (done) return
    done = true
    stop()
    then(user)
  }
  const token = localStorage.getItem("authToken")
  const stop = useAuthStore.subscribe((state) => {
    if (state.user) once(state.user)
    else if (!state.isAuthenticated) {
      done = true
      stop()
    }
  })
  signedIn?.then(
    (user) => {
      if (localStorage.getItem("authToken") === token && useAuthStore.getState().isAuthenticated) once(user)
    },
    () => {}
  )
}

/**
 * At startup, before React renders: once the sign-in check has answered, start the code and the first data of the
 * page at the address the app opened on (only while the person is still on that address); and let links
 * start a page's code when pointed at (lib/route-preload.ts preloadRouteIntent). The small module that asks for
 * the data loads at once.
 *
 * The code waits for the sign-in check (measured 4 Nov, A/B on localhost: a page's code started before it sent
 * up to 80 script requests that held the browser's 6 connections and delayed the check by 0.7-1.7 s; on plain
 * http the live site has the same 6). It starts the moment the check answers, not after the data's module
 * (waiting for that module started a phone summary's code 0.4 s later than the page itself would).
 */
export function preloadCurrentRoute(
  pathname = window.location.pathname,
  search = window.location.search,
  signedIn: Promise<User> | null = null,
  steps: { data: boolean; code: boolean } = { data: true, code: true }
): boolean {
  if (steps.code) registerRouteTree(appRouteTree)
  // Signed out, every private address goes to the sign-in page: its page's code would be downloaded for nothing.
  if (!localStorage.getItem("authToken") || (!steps.data && !steps.code)) return false
  const tree = appRouteTree()
  const page = steps.code ? routePageFor(tree, pathname) : null
  const data = steps.data ? routeDataFor(tree, pathname) : null
  const module = data?.load()
  module?.catch(() => {}) // the page asks for its own data as before
  if (!page && !data) return false
  whenSignedIn(signedIn, (user) => {
    if (window.location.pathname !== pathname) return
    page?.preload("start")
    void module?.then(({ prefetch }) => {
      if (window.location.pathname !== pathname) return
      prefetch({ client: queryClient, params: data!.params, search: new URLSearchParams(search), user })
    }, () => {})
  })
  return true
}
