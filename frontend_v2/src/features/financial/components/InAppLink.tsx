import type { ReactNode } from "react"
import { Link, useInRouterContext } from "react-router-dom"

/**
 * A link to another page of this app. Inside the router it navigates without
 * reloading the app, so what the browser already read (the ledger, the
 * judgement calls) is still there when the user comes Back; a plain anchor
 * reloads everything and the ledger is read again from the server. Outside a
 * router (isolated component tests) it is a plain anchor to the same address.
 */
export function InAppLink({
  to,
  className,
  children,
  onClick,
}: {
  to: string
  className?: string
  children: ReactNode
  onClick?: () => void
}) {
  if (!useInRouterContext())
    return (
      <a className={className} href={to} onClick={onClick}>
        {children}
      </a>
    )
  return (
    <Link className={className} to={to} onClick={onClick}>
      {children}
    </Link>
  )
}
