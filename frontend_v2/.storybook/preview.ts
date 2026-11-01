import type { Preview } from "@storybook/react-vite"
import "../src/styles/globals.css"

const preview: Preview = {
  parameters: {
    backgrounds: { disable: true },
    controls: {
      matchers: {
        color: /(background|color)$/i,
        date: /Date$/i,
      },
    },
    a11y: {
      test: "todo",
    },
  },
  // Theme per story or from the toolbar; dark stays the default. Phone kit stories run in both (07 section 5).
  globalTypes: {
    theme: {
      description: "Colour theme",
      toolbar: { title: "Theme", items: ["light", "dark"], dynamicTitle: true },
    },
  },
  initialGlobals: { theme: "dark" },
  decorators: [
    (Story, context) => {
      const theme = context.parameters.theme ?? context.globals.theme ?? "dark"
      document.documentElement.classList.toggle("dark", theme === "dark")
      return Story()
    },
  ],
}

export default preview
