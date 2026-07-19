import { useEffect, useState, type ReactNode } from "react"
import { ThemeContext, type Theme } from "./theme"

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setTheme] = useState<Theme>(
    () => (localStorage.getItem("owl-theme") as Theme) ?? "dark"
  )

  useEffect(() => {
    const root = document.documentElement
    root.classList.remove("dark", "light")

    if (theme === "system") {
      const systemDark = window.matchMedia(
        "(prefers-color-scheme: dark)"
      ).matches
      root.classList.add(systemDark ? "dark" : "light")
    } else {
      root.classList.add(theme)
    }

    localStorage.setItem("owl-theme", theme)
  }, [theme])

  return (
    <ThemeContext.Provider value={{ theme, setTheme }}>
      {children}
    </ThemeContext.Provider>
  )
}
