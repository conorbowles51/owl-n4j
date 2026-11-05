import { createRoutesFromChildren, type RouteObject } from "react-router-dom"
import { AppRoutes } from "./routes"

let tree: RouteObject[] | null = null

/** app/routes.tsx's <Route> tree as react-router route objects (read once; AppRoutes holds no hooks). */
export function appRouteTree(): RouteObject[] {
  if (!tree) tree = createRoutesFromChildren((AppRoutes() as { props: { children: React.ReactNode } }).props.children)
  return tree
}
