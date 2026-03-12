import { useMemo } from "react"

function isDarkMode(): boolean {
  return document.documentElement.classList.contains("dark")
}

export function useMapTheme() {
  const isDark = useMemo(() => isDarkMode(), [])

  const styleUrl = isDark
    ? "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json"
    : "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json"

  return { styleUrl, isDark }
}
