/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // Owl Consultancy Group color scheme
        owl: {
          // Dark blue (primary)
          blue: {
            50: '#e8f0f7',
            100: '#c5d9ec',
            200: '#9ebfdf',
            300: '#75a5d2',
            400: '#5591c8',
            500: '#357dbe',
            600: '#2d6fa8',
            700: '#245e8f',
            800: '#1d4d76',
            900: '#0f2f4a', // Main dark blue
          },
          // Purple (accent)
          purple: {
            50: '#f3e8ff',
            100: '#e9d5ff',
            200: '#d8b4fe',
            300: '#c084fc',
            400: '#a855f7',
            500: '#9333ea', // Main purple
            600: '#7c3aed',
            700: '#6b21a8',
            800: '#581c87',
            900: '#3b0764',
          },
          // Orange (accent)
          orange: {
            50: '#fff7ed',
            100: '#ffedd5',
            200: '#fed7aa',
            300: '#fdba74',
            400: '#fb923c',
            500: '#f97316', // Main orange
            600: '#ea580c',
            700: '#c2410c',
            800: '#9a3412',
            900: '#7c2d12',
          },
        },
        // Light theme grays
        light: {
          50: '#f9fafb',
          100: '#f3f4f6',
          200: '#e5e7eb',
          300: '#d1d5db',
          400: '#9ca3af',
          500: '#6b7280',
          600: '#4b5563',
          700: '#374151',
          800: '#1f2937',
          900: '#111827',
        },
      },
    },
  },
  plugins: [],
}
