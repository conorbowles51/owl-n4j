import { createRoutesFromChildren, type RouteObject } from "react-router-dom"
import { useAuthStore } from "@/features/auth/hooks/use-auth"
import type { User } from "@/features/auth/auth.types"
import { queryClient } from "@/lib/query-client"
import { preloadRoute, registerRouteTree, routeDataFor } from "@/lib/route-preload"
import { AppRoutes } from "./routes"

let tree: RouteObject[] | null = null

/** app/routes.tsx's <Route> tree as react-router route objects (read once; AppRoutes holds no hooks). */
export function appRouteTree(): RouteObject[] {
  if (!tree) tree = createRoutesFromChildren((AppRoutes() as { props: { children: React.ReactNode } }).props.children)
  return tree
}

/**
 * Calls `then` once the sign-in check (ProtectedRoute's /api/auth/me) has answered with the signed-in person:
 * requests that need the session wait for it exactly as the page's own do. Never if the person is signed out
 * first.
 */
function whenSignedIn(then: (user: User) => void) {
  const now = useAuthStore.getState()
  if (now.user) return then(now.user)
  const stop = useAuthStore.subscribe((state) => {
    if (state.user) {
      stop()
      then(state.user)
    } else if (!state.isAuthenticated) stop()
  })
}

/**
 * At startup, before React renders: start the code of the page at the address the app opened on and, once the
 * sign-in check has answered, the page's first data (only while the person is still on that address); and let
 * links start a page's code when pointed at (lib/route-preload.ts preloadRouteIntent).
 */
export function preloadCurrentRoute(pathname = window.location.pathname, search = window.location.search): boolean {
  registerRouteTree(appRouteTree)
  // Signed out, every private address goes to the sign-in page: its page's code would be downloaded for nothing.
  if (!localStorage.getItem("authToken")) return false
  const code = preloadRoute(appRouteTree(), pathname, "start")
  const data = routeDataFor(appRouteTree(), pathname)
  if (data) {
    const module = data.load()
    module.catch(() => {}) // the page asks for its own data as before
    whenSignedIn((user) => {
      if (window.location.pathname !== pathname) return
      void module.then(({ prefetch }) => {
        if (window.location.pathname !== pathname) return
        prefetch({ client: queryClient, params: data.params, search: new URLSearchParams(search), user })
      }, () => {})
    })
  }
  return code || !!data
}
