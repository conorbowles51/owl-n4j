import { useQuery } from "@tanstack/react-query"
import { useState } from "react"
import { comparePhones, failureText, type PhoneComparison } from "../api"

const fmt = (n: number) => n.toLocaleString("en-US")
const KIND_WORDS = { message: ["message", "messages"], call: ["call", "calls"] } as const

/**
 * Compare two phones (07 J-16): one column per phone and the matched records between them, for messages and for
 * calls: on both, only on one (with how many fall outside the other phone's period), only on the other.
 */
export function ComparePhones({ caseId, phones, first, second, person = null }: {
  caseId: string
  phones: { extraction_id: string; label: string }[]
  first?: string
  second?: string
  /** One identity: only what each phone holds with this person (07 J-16). */
  person?: string | null
}) {
  const known = (id?: string) => (id && phones.some((p) => p.extraction_id === id) ? id : undefined)
  const [a, setA] = useState(known(first) ?? phones[0]?.extraction_id ?? "")
  const [b, setB] = useState(known(second) ?? phones[1]?.extraction_id ?? "")
  const res = useQuery({
    queryKey: ["phone-compare", caseId, a, b, person],
    queryFn: ({ signal }) => comparePhones(caseId, a, b, person, signal),
    enabled: !!a && !!b && a !== b,
    retry: false,
  })
  const pick = (value: string, set: (v: string) => void, name: string) => (
    <label className="flex items-center gap-1.5 text-sm">
      {name}
      <select className="rounded border bg-background px-2 py-1" value={value} onChange={(e) => set(e.target.value)}>
        {phones.map((p) => (
          <option key={p.extraction_id} value={p.extraction_id}>
            {p.label}
          </option>
        ))}
      </select>
    </label>
  )
  return (
    <section aria-label="Compare phones" className="flex flex-col gap-2 rounded border p-3">
      <div className="flex flex-wrap items-center gap-3">
        {pick(a, setA, "First phone")}
        {pick(b, setB, "Second phone")}
      </div>
      {a === b && <p className="text-sm">Choose two different phones.</p>}
      {res.isLoading && <p role="status" className="text-sm">Comparing the phones</p>}
      {res.isError && <p role="alert" className="text-sm">{failureText(res.error, "The phones could not be compared.")}</p>}
      {res.data && <Comparison data={res.data} />}
    </section>
  )
}

function Comparison({ data }: { data: PhoneComparison }) {
  const A = data.a.label
  const B = data.b.label
  return (
    <div className="flex flex-col gap-2 text-sm">
      <table className="w-full table-fixed border-collapse">
        <thead>
          <tr className="text-left text-xs text-muted-foreground">
            <th scope="col" className="p-1">Only on {A}</th>
            <th scope="col" className="p-1">On both</th>
            <th scope="col" className="p-1">Only on {B}</th>
          </tr>
        </thead>
        <tbody>
          {(["message", "call"] as const).map((k) => {
            const c = data.kinds[k]
            const [one, many] = KIND_WORDS[k]
            const w = (n: number) => (n === 1 ? one : many)
            return (
              <tr key={k} className="border-t align-top">
                <td className="p-1">
                  <span>
                    {fmt(c.only_a)} only on {A}
                  </span>{" "}
                  {w(c.only_a)}
                  {c.only_a_outside > 0 && <span className="block text-xs text-muted-foreground">{fmt(c.only_a_outside)} outside {B}'s period</span>}
                </td>
                <td className="p-1">
                  <span>{fmt(c.both)} on both</span> {w(c.both)}
                </td>
                <td className="p-1">
                  <span>
                    {fmt(c.only_b)} only on {B}
                  </span>{" "}
                  {w(c.only_b)}
                  {c.only_b_outside > 0 && <span className="block text-xs text-muted-foreground">{fmt(c.only_b_outside)} outside {A}'s period</span>}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
      <p className="text-xs text-muted-foreground">{data.key}</p>
      {[data.a, data.b]
        .filter((s) => s.no_time > 0)
        .map((s) => (
          <p key={s.extraction_id} className="text-xs">
            {fmt(s.no_time)} messages and calls on {s.label} have no time and are not compared.
          </p>
        ))}
    </div>
  )
}
