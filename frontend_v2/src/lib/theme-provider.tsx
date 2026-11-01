import { useEffect, useState, type ReactNode } from "react"
import { ThemeContext, type Theme } from "./theme-context"

/** The saved theme, or dark. A browser that refuses site storage (blocked cookies, some private modes) throws. */
function getStoredTheme(): Theme {
  let stored: string | null = null
  try {
    stored = localStorage.getItem("owl-theme")
  } catch {
    // storage refused: the default theme, not a blank page
  }
  return stored === "light" || stored === "system" || stored === "dark"
    ? stored
    : "dark"
}

function storeTheme(theme: Theme) {
  try {
    storeTheme(theme)
  } catch {
    // storage refused or full: the theme still applies for this visit
  }
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setTheme] = useState<Theme>(getStoredTheme)

  useEffect(() => {
    const root = document.documentElement
    const systemPreference = window.matchMedia("(prefers-color-scheme: dark)")
    const themeColor = document.querySelector<HTMLMetaElement>(
      'meta[name="theme-color"]'
    )

    const applyTheme = () => {
      const resolved =
        theme === "system"
          ? systemPreference.matches
            ? "dark"
            : "light"
          : theme

      root.classList.remove("dark", "light")
      root.classList.add(resolved)
      themeColor?.setAttribute(
        "content",
        resolved === "dark" ? "#0B0C0F" : "#F7F7F8"
      )
    }

    applyTheme()
    storeTheme(theme)

    if (theme === "system") {
      systemPreference.addEventListener("change", applyTheme)
      return () => systemPreference.removeEventListener("change", applyTheme)
    }
  }, [theme])

  return (
    <ThemeContext.Provider value={{ theme, setTheme }}>
      {children}
    </ThemeContext.Provider>
  )
}
