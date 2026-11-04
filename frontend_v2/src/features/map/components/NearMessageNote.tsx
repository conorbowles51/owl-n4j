import { Link } from "react-router-dom"
import type { PhoneMapNear } from "@/features/phones/api"

/**
 * The note over the map after Show on Map from a message (03 section 3.6 item 7): how many positioned records on the
 * same phone fall within the hour of the message, and when there are none, how far in time the nearest one is with a
 * link to it. Only the hour's positions are drawn while the note shows, and it says so.
 */
export function NearMessageNote({ loading, failed, near }: { loading: boolean; failed: boolean; near: PhoneMapNear | undefined }) {
  return (
    <p role="status" className="absolute left-2 top-2 z-10 max-w-md rounded border bg-card px-2 py-1 text-xs shadow-sm">
      {loading && "Finding the positions near this message"}
      {failed && "The positions near this message could not be found."}
      {near?.words}
      {near?.nearest && (
        <>
          {" "}
          <Link className="underline underline-offset-2" to={`?phone_point=${near.nearest.lon},${near.nearest.lat}`}>
            Show it
          </Link>
          .
        </>
      )}
      {near && near.within > 0 && (
        <>
          {" "}Only those are drawn.{" "}
          <Link className="underline underline-offset-2" to="?">
            Show every position
          </Link>
        </>
      )}
    </p>
  )
}
