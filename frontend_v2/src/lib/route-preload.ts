import { isValidElement, type ReactNode } from "react"
import { matchRoutes, type RouteObject } from "react-router-dom"

/**
 * Start a lazy route page's code when a link to it is pointed at (hover or keyboard focus).
 *
 * The route table is app/routes.tsx itself (its <Route> tree, read with react-router's own matcher, so the page
 * chosen is the page React will render, ranked the same way). No second list of addresses exists to drift.
 *
 * Fresh loads do not start anything before render: sending the sign-in check, a page's first data or its code at
 * start-up was measured live on the 8 most-viewed pages (LX-ROUTEPRELOAD-STATUS.md E) and did not reliably open
 * them sooner, and first paint came later.
 */

type Preloadable = { preload: () => void }

function preloadableIn(node: ReactNode): Preloadable | null {
  if (!isValidElement(node)) return null
  const type = node.type as unknown as Partial<Preloadable> | string
  if (typeof type !== "string" && typeof type?.preload === "function") return type as Preloadable
  const children = (node.props as { children?: ReactNode }).children
  for (const child of Array.isArray(children) ? children : [children]) {
    const found = preloadableIn(child)
    if (found) return found
  }
  return null
}

/** The lazy page the route tree renders at `pathname`, or null (no match, a redirect, or a page in the shell). */
export function routePageFor(routes: RouteObject[], pathname: string): Preloadable | null {
  const matches = matchRoutes(routes, pathname)
  const leaf = matches?.at(-1)?.route
  return leaf ? preloadableIn(leaf.element) : null
}

let routeTree: (() => RouteObject[]) | null = null

/** main.tsx registers the app's route tree (so links need not import every page). */
export function registerRouteTree(tree: () => RouteObject[]) {
  routeTree = tree
}

/**
 * A link to `to` is pointed at (hover or keyboard focus): start that page's code only, never its data, and never
 * before the app has registered its routes. Returns whether a page's code was asked for.
 */
export function preloadRouteIntent(to: string): boolean {
  if (!routeTree) return false
  const page = routePageFor(routeTree(), to.split(/[?#]/)[0])
  page?.preload()
  return Boolean(page)
}
