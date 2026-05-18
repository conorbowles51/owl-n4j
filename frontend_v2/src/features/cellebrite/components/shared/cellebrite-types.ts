export type CommsSeed = {
  id: string
  reportKey?: string
  reportKeys?: string[]
  participantKeys: string[]
  type: "all" | "message" | "call" | "email"
  label: string
}
