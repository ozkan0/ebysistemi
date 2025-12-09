/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        // Override default 'sans' with JetBrains Mono
        sans: ['"JetBrains Mono"', 'monospace', 'ui-sans-serif', 'system-ui'],
      },
      colors: {
        slate: {
          950: '#020617',
          900: '#0f172a',
          800: '#1e293b',
          700: '#334155',
          100: '#f1f5f9',
        },
        red: { 600: '#ef4444' },
        amber: { 500: '#f59e0b' },
        orange: { 500: '#f97316' },
        green: { 500: '#22c55e' },
        cyan: { 500: '#06b6d4' },
      },
    },
  },
  plugins: [],
}