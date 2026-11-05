import { z } from "zod"

const expertPacketSchema = z.object({
  completeness: z.enum(["complete_expert_packet", "incomplete_expert_packet"]),
  byte_count: z.number().int().nonnegative(),
  sentence: z.string(),
  parts: z.array(z.object({ label: z.string(), holds: z.boolean() })),
})

export type ExpertPacket = z.infer<typeof expertPacketSchema>

/** The export's own statement of its parts; a download without one shows no claim at all. */
export function readExpertPacket(header: string | null): ExpertPacket | null {
  if (!header) return null
  try {
    return expertPacketSchema.parse(JSON.parse(header))
  } catch {
    return null
  }
}
