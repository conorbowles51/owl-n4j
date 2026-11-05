import { describe, expect, it } from "vitest"
import type { ParticipantLabelData } from "../schemas"
import { otherParty, pairPath, peoplePath, personPath } from "./participant-menu"

/** 03 section 6.7: each action of a participant label lands on the right scope. Invented identifiers. */
const label = (key: string | null, is_owner = false): ParticipantLabelData =>
  ({ identity_key: key, name: null, name_basis: "none", identifier: null, is_owner, owner_basis: null, case_names: [] })
const A = label("phone:+12025550143"), B = label("phone:+12025550188"), OWNER = label(null, true), NOBODY = label(null)
const params = (path: string | null) => new URL(path!, "http://x").searchParams

describe("participant menu scopes", () => {
  it("Show all with this person is the person on every phone", () => {
    const q = params(personPath("c", A.identity_key!))
    expect(personPath("c", A.identity_key!).startsWith("/cases/c/conversations?")).toBe(true)
    expect(q.get("tab")).toBe("people")
    expect(q.get("people")).toBe("phone:+12025550143")
    expect(q.get("phones")).toBeNull()
  })

  it("Show this pair is both people, read as between them", () => {
    const q = params(pairPath("c", A.identity_key!, B))
    expect(q.get("people")).toBe("phone:+12025550143,phone:+12025550188")
    expect(q.get("mode")).toBe("between")
  })

  it("the owner with no identifier is the between reading of one person", () => {
    const q = params(pairPath("c", A.identity_key!, OWNER))
    expect(q.get("people")).toBe("phone:+12025550143")
    expect(q.get("mode")).toBe("between")
  })

  it("no second person gives no pair", () => {
    expect(pairPath("c", A.identity_key!, null)).toBeNull()
    expect(pairPath("c", A.identity_key!, NOBODY)).toBeNull()
  })

  it("the other party is the sender for a recipient and a recipient for the sender", () => {
    expect(otherParty({ from: A, to: [B] }, B)).toBe(A)
    expect(otherParty({ from: A, to: [A, B] }, A)).toBe(B)
    expect(otherParty({ from: A, to: [] }, A)).toBeNull()
  })

  it("Open in People goes to the linked person, or to linking when there is none", () => {
    expect(peoplePath("c", "phone:+1", "d1")).toBe("/cases/c/dossiers?dossier=d1")
    const q = params(peoplePath("c", "phone:+1", null))
    expect(q.get("decision")).toBe("link_phone_identity")
    expect(q.get("identity")).toBe("phone:+1")
  })
})
