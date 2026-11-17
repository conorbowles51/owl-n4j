import { useEffect, useState } from "react"
import { useParams } from "react-router-dom"
import type { RelationMember } from "@/features/relations/api"
import { isTyping, memberFromElement } from "./item-target"
import { QuestionMenu } from "./QuestionMenu"
import { addPart } from "./selection-store"

/**
 * Right-click or the key C on any item that names itself with data-corro (lx-corroselect C). Right-click opens a
 * one-item menu at the pointer (Shift+right-click keeps the browser's own menu); C acts on the item under the pointer,
 * or the focused one. One click or key reaches the question menu; the item also joins the selection.
 */
export function ItemKeys() {
  const { id: caseId } = useParams()
  const [menu, setMenu] = useState<{ x: number; y: number; member: RelationMember } | null>(null)
  const [open, setOpen] = useState(false)
  useEffect(() => {
    if (!caseId) return
    let hover: Element | null = null
    const start = (member: RelationMember) => {
      addPart(caseId, { screen: "an item", label: member.label ?? "1 item", members: [member], skipped: [] })
      setMenu(null)
      setOpen(true)
    }
    const move = (e: MouseEvent) => { hover = e.target as Element }
    const context = (e: MouseEvent) => {
      if (e.shiftKey) return
      const member = memberFromElement(e.target as Element)
      if (!member) return setMenu(null)
      e.preventDefault()
      setMenu({ x: e.clientX, y: e.clientY, member })
    }
    const key = (e: KeyboardEvent) => {
      if (e.key === "Escape") return setMenu(null)
      if ((e.key !== "c" && e.key !== "C") || e.ctrlKey || e.metaKey || e.altKey || isTyping(e.target)) return
      const member = memberFromElement(document.activeElement && document.activeElement !== document.body ? document.activeElement : hover)
        ?? memberFromElement(hover)
      if (member) {
        e.preventDefault()
        start(member)
      }
    }
    const away = () => setMenu(null)
    document.addEventListener("mousemove", move, { passive: true })
    document.addEventListener("contextmenu", context)
    document.addEventListener("keydown", key)
    document.addEventListener("click", away)
    return () => {
      document.removeEventListener("mousemove", move)
      document.removeEventListener("contextmenu", context)
      document.removeEventListener("keydown", key)
      document.removeEventListener("click", away)
    }
  }, [caseId])
  if (!caseId) return null
  return (
    <>
      {menu && (
        <div role="menu" style={{ left: Math.min(menu.x, window.innerWidth - 220), top: Math.min(menu.y, window.innerHeight - 60) }}
          className="fixed z-50 rounded-md border bg-background py-1 text-sm shadow-md">
          <button role="menuitem" type="button" className="block w-52 px-3 py-1.5 text-left hover:bg-muted"
            onClick={() => { addPart(caseId, { screen: "an item", label: menu.member.label ?? "1 item", members: [menu.member], skipped: [] }); setMenu(null); setOpen(true) }}>
            Corroborate this <span className="text-muted-foreground">(C)</span>
          </button>
        </div>
      )}
      {open && <QuestionMenu caseId={caseId} onClose={() => setOpen(false)} />}
    </>
  )
}
