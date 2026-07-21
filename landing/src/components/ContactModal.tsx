import { useEffect, useRef, useState, type FormEvent } from "react"

interface ContactModalProps {
  open: boolean
  onClose: () => void
}
export function ContactModal({ open, onClose }: ContactModalProps) {
  const dialogRef = useRef<HTMLDivElement>(null)
  const firstFieldRef = useRef<HTMLInputElement>(null)
  const [draftOpened, setDraftOpened] = useState(false)

  useEffect(() => {
    if (!open) return
    const previous = document.activeElement as HTMLElement | null
    document.body.classList.add("modal-open")
    requestAnimationFrame(() => firstFieldRef.current?.focus())

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onClose()
        return
      }
      if (event.key !== "Tab" || !dialogRef.current) return
      const focusable = dialogRef.current.querySelectorAll<HTMLElement>(
        "button, input, textarea, a[href]"
      )
      const first = focusable[0]
      const last = focusable[focusable.length - 1]
      if (!first || !last) return
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault()
        first.focus()
      }
    }
    document.addEventListener("keydown", onKeyDown)
    return () => {
      document.body.classList.remove("modal-open")
      document.removeEventListener("keydown", onKeyDown)
      previous?.focus()
      setDraftOpened(false)
    }
  }, [open, onClose])

  if (!open) return null

  const onSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const data = new FormData(event.currentTarget)
    const recipient = import.meta.env.VITE_CONTACT_EMAIL || ""
    const subject = encodeURIComponent("Loupe walkthrough request")
    const body = encodeURIComponent(
      `Name: ${data.get("name")}\nOrganisation: ${data.get("organisation")}\nEmail: ${data.get("email")}\n\nWhat I would like to explore:\n${data.get("message")}`
    )
    window.location.href = `mailto:${recipient}?subject=${subject}&body=${body}`
    setDraftOpened(true)
  }

  return (
    <div className="modal-backdrop" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <div className="contact-modal" ref={dialogRef} role="dialog" aria-modal="true" aria-labelledby="contact-title">
        <button className="modal-close" type="button" onClick={onClose} aria-label="Close dialog">×</button>
        <p className="section-index">Private walkthrough</p>
        <h2 id="contact-title">See Loupe in motion.</h2>
        <p className="contact-intro">
          Tell us what you want to make sense of. Submitting opens a prepared request in your email client.
        </p>
        <form onSubmit={onSubmit}>
          <label><span>Name</span><input ref={firstFieldRef} name="name" type="text" autoComplete="name" required /></label>
          <label><span>Work email</span><input name="email" type="email" autoComplete="email" required /></label>
          <label><span>Organisation</span><input name="organisation" type="text" autoComplete="organization" /></label>
          <label><span>What would you like to explore?</span><textarea name="message" rows={4} required /></label>
          <button className="button button-primary modal-submit" type="submit">Prepare request <span aria-hidden="true">↗</span></button>
          {draftOpened && <p className="draft-status" role="status">Your email draft has been opened.</p>}
        </form>
      </div>
    </div>
  )
}
