import { useEffect, useState } from "react"

type Theme = "dark" | "light"

const THEME_STORAGE_KEY = "loupe-theme"

function getInitialTheme(): Theme {
  if (typeof document === "undefined") return "dark"
  return document.documentElement.dataset.theme === "light" ? "light" : "dark"
}

export function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>(getInitialTheme)
  const isLight = theme === "light"

  useEffect(() => {
    document.documentElement.dataset.theme = theme
    document
      .querySelector('meta[name="theme-color"]')
      ?.setAttribute("content", isLight ? "#f7f7f8" : "#0b0c0f")

    try {
      window.localStorage.setItem(THEME_STORAGE_KEY, theme)
    } catch {
      // The selected theme still applies when storage is unavailable.
    }
  }, [isLight, theme])

  return (
    <button
      className={`theme-toggle ${isLight ? "is-light" : ""}`}
      type="button"
      aria-label={`Switch to ${isLight ? "dark" : "light"} theme`}
      aria-pressed={isLight}
      title={`Switch to ${isLight ? "dark" : "light"} theme`}
      onClick={() => setTheme(isLight ? "dark" : "light")}
    >
      <span className="theme-toggle-indicator" aria-hidden="true" />
      <svg className="theme-toggle-icon theme-toggle-sun" viewBox="0 0 20 20" aria-hidden="true">
        <circle cx="10" cy="10" r="3.1" />
        <path d="M10 2.1v1.5M10 16.4v1.5M2.1 10h1.5M16.4 10h1.5M4.4 4.4l1.1 1.1M14.5 14.5l1.1 1.1M15.6 4.4l-1.1 1.1M5.5 14.5l-1.1 1.1" />
      </svg>
      <svg className="theme-toggle-icon theme-toggle-moon" viewBox="0 0 20 20" aria-hidden="true">
        <path d="M15.7 12.7A6.4 6.4 0 0 1 7.3 4.3a6.4 6.4 0 1 0 8.4 8.4Z" />
      </svg>
      <span className="sr-only">{isLight ? "Light" : "Dark"} theme active</span>
    </button>
  )
}
