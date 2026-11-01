export interface Journey {
  id: string
  owner: string
  gate: string
  title: string
  run: (ctx: unknown) => Promise<void>
}
export const ALL: Journey[]
