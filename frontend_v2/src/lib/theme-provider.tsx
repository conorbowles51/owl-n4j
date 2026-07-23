import { useEffect, useState, type ReactNode } from "react"
import { ThemeContext, type Theme } from "./theme-context"

function getStoredTheme(): Theme {
  const stored = localStorage.getItem("owl-theme")
  return stored === "light" || stored === "system" || stored === "dark"
    ? stored
    : "dark"
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
    localStorage.setItem("owl-theme", theme)

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
