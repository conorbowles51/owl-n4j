/** The `phone_together` setting (lx-phonetogether). Off until Neil approves the mock-up; a build sets
 * VITE_PHONE_TOGETHER=on, and a person can see it ahead of that with `?phone_together=on` in the address (kept in this
 * browser) or `=off` to clear it. It shows only where the phone layers (`phone_layers`) are on too. Kept apart from the
 * read so a screen that only asks "is it on" loads none of the overlay code. */
export function phoneTogetherEnabled(): boolean {
  try {
    const q = new URLSearchParams(window.location.search).get("phone_together")
    if (q === "on") localStorage.setItem("loupe.phone_together", "on")
    if (q === "off") localStorage.removeItem("loupe.phone_together")
    return import.meta.env.VITE_PHONE_TOGETHER === "on" || localStorage.getItem("loupe.phone_together") === "on"
  } catch {
    return import.meta.env.VITE_PHONE_TOGETHER === "on"
  }
}

