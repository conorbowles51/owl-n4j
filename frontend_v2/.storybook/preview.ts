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
  decorators: [
    (Story) => {
      document.documentElement.classList.add("dark")
      return Story()
    },
  ],
}

export default preview
