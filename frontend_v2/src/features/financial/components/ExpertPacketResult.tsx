import { formatBytes } from "@/features/evidence/upload-progress"
import type { ExpertPacket } from "../lib/expert-packet"

/** What one finished download holds, as the server stated it for that export. */
export function ExpertPacketResult({ packet }: { packet: ExpertPacket | null }) {
  if (!packet) return null
  return (
    <div aria-label="Expert packet parts in this export" className="text-sm">
      <p>
        {packet.sentence} Download size: {formatBytes(packet.byte_count)}.
      </p>
      <ul className="list-disc pl-5">
        {packet.parts.map((part) => (
          <li key={part.label}>
            {part.label}: {part.holds ? "complete" : "incomplete"}
          </li>
        ))}
      </ul>
    </div>
  )
}
