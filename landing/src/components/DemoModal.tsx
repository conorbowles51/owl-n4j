import { useEffect, useRef, useState, type FormEvent } from 'react';
import { submitDemoRequest } from '../lib/demoRequest';

interface DemoModalProps {
  open: boolean;
  onClose: () => void;
}

type Status = 'idle' | 'submitting' | 'done' | 'error';

export function DemoModal({ open, onClose }: DemoModalProps) {
  const dialogRef = useRef<HTMLDivElement>(null);
  const firstFieldRef = useRef<HTMLInputElement>(null);
  const [status, setStatus] = useState<Status>('idle');

  useEffect(() => {
    if (!open) return;
    document.body.style.overflow = 'hidden';
    const previouslyFocused = document.activeElement as HTMLElement | null;
    firstFieldRef.current?.focus();

    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose();
        return;
      }
      if (e.key !== 'Tab' || !dialogRef.current) return;
      // simple focus trap
      const focusables = dialogRef.current.querySelectorAll<HTMLElement>(
        'button, input, textarea, [href]',
      );
      if (focusables.length === 0) return;
      const first = focusables[0];
      const last = focusables[focusables.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    };
    document.addEventListener('keydown', onKeyDown);

    return () => {
      document.body.style.overflow = '';
      document.removeEventListener('keydown', onKeyDown);
      previouslyFocused?.focus();
    };
  }, [open, onClose]);

  if (!open) return null;

  const handleSubmit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const form = e.currentTarget;
    const data = new FormData(form);
    setStatus('submitting');
    try {
      await submitDemoRequest({
        name: String(data.get('name') ?? ''),
        email: String(data.get('email') ?? ''),
        firm: String(data.get('firm') ?? ''),
        message: String(data.get('message') ?? ''),
      });
      setStatus('done');
    } catch {
      setStatus('error');
    }
  };

  return (
    <div className="modal-overlay" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div
        ref={dialogRef}
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="demo-modal-title"
      >
        <button type="button" className="modal-close" onClick={onClose} aria-label="Close">
          ×
        </button>

        {status === 'done' ? (
          <div className="modal-done">
            <p className="kicker">Request received</p>
            <h2 id="demo-modal-title" className="modal-title">
              We’ll be in touch.
            </h2>
            <p className="modal-sub">
              Thanks — someone from the team will reach out to schedule your demo.
            </p>
            <button type="button" className="btn btn-ghost" onClick={onClose}>
              Close
            </button>
          </div>
        ) : (
          <>
            <p className="kicker">Book a demo</p>
            <h2 id="demo-modal-title" className="modal-title">
              See your casework, illuminated.
            </h2>
            <p className="modal-sub">
              Tell us a little about your firm and we’ll set up a walkthrough with a working case.
            </p>
            <form className="modal-form" onSubmit={handleSubmit}>
              <label className="field">
                <span className="field-label">Name</span>
                <input ref={firstFieldRef} name="name" type="text" required autoComplete="name" />
              </label>
              <label className="field">
                <span className="field-label">Work email</span>
                <input name="email" type="email" required autoComplete="email" />
              </label>
              <label className="field">
                <span className="field-label">Firm</span>
                <input name="firm" type="text" autoComplete="organization" />
              </label>
              <label className="field">
                <span className="field-label">What kind of casework do you do?</span>
                <textarea name="message" rows={3} />
              </label>
              {status === 'error' && (
                <p className="modal-error">Something went wrong — please try again.</p>
              )}
              <button
                type="submit"
                className="btn btn-primary modal-submit"
                disabled={status === 'submitting'}
              >
                {status === 'submitting' ? 'Sending…' : 'Request a demo'}
              </button>
            </form>
          </>
        )}
      </div>
    </div>
  );
}
