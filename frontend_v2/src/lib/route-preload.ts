import { isValidElement, type ReactNode } from "react"
import type { QueryClient } from "@tanstack/react-query"
import { matchRoutes, type Params, type RouteObject } from "react-router-dom"
import type { User } from "@/features/auth/auth.types"
import type { PreloadReason } from "./timed-lazy"

/** What a route's first-data prefetch is given: the app's cache, the address it opened on, the signed-in person. */
export interface RouteDataContext {
  client: QueryClient
  params: Params<string>
  search: URLSearchParams
  user: User
}

/**
 * A route's first data, started alongside its code: a module (loaded at start-up, beside the page's code) whose
 * `prefetch` asks for the page's first requests with the same query keys and fetchers the page uses, so the page
 * finds them in the cache (or in flight) and never asks twice.
 */
export type RouteDataLoader = () => Promise<{ prefetch: (context: RouteDataContext) => void }>

/**
 * Start a lazy route page's code before React asks for it.
 *
 * The route table is app/routes.tsx itself (its <Route> tree, read with react-router's own matcher, so the page
 * chosen is the page React will render, ranked the same way). No second list of addresses exists to drift.
 *
 * Measured 4 Nov (signed in, live, 8 most-viewed pages): on a fresh load a page's code was asked for only after the
 * shell had run and the sign-in check had answered (1.4-4.0 s after opening), and the page's data only after that
 * code had arrived and mounted. Starting the code from main.tsx lets it download alongside the shell.
 */

type Preloadable = { preload: (reason: PreloadReason) => void }

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

function routeDataIn(node: ReactNode): RouteDataLoader | null {
  if (!isValidElement(node)) return null
  const props = node.props as { data?: unknown; children?: ReactNode }
  if (typeof props.data === "function") return props.data as RouteDataLoader
  for (const child of Array.isArray(props.children) ? props.children : [props.children]) {
    const found = routeDataIn(child)
    if (found) return found
  }
  return null
}

/** The page's first-data loader (the `data` given to its route element) and the address's params, or null. */
export function routeDataFor(routes: RouteObject[], pathname: string): { load: RouteDataLoader; params: Params<string> } | null {
  const matches = matchRoutes(routes, pathname)
  const leaf = matches?.at(-1)
  const load = leaf ? routeDataIn(leaf.route.element) : null
  return load && leaf ? { load, params: leaf.params } : null
}

/** The lazy page the route tree renders at `pathname`, or null (no match, a redirect, or a page in the shell). */
export function routePageFor(routes: RouteObject[], pathname: string): Preloadable | null {
  const matches = matchRoutes(routes, pathname)
  const leaf = matches?.at(-1)?.route
  return leaf ? preloadableIn(leaf.element) : null
}

/** Starts the code of the page at `pathname` ("start": the page being opened; "intent": a link pointed at). */
export function preloadRoute(routes: RouteObject[], pathname: string, reason: PreloadReason): boolean {
  const page = routePageFor(routes, pathname)
  if (!page) return false
  page.preload(reason)
  return true
}

let routeTree: (() => RouteObject[]) | null = null

/** app/route-table.ts registers the app's route tree at startup (so links need not import every page). */
export function registerRouteTree(tree: () => RouteObject[]) {
  routeTree = tree
}

/**
 * A link to `to` is pointed at (hover or keyboard focus): start that page's code only, never its data, and never
 * before the app has registered its routes. Returns whether a page's code was asked for.
 */
export function preloadRouteIntent(to: string): boolean {
  if (!routeTree) return false
  const pathname = to.split(/[?#]/)[0]
  return preloadRoute(routeTree(), pathname, "intent")
}
