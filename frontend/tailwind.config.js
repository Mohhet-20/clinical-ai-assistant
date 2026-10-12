/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      fontFamily: { sans: ['"DM Sans"', 'ui-sans-serif', 'system-ui', 'sans-serif'], mono: ['"DM Mono"', 'ui-monospace', 'monospace'] },
      colors: { brand: { 50: '#effaf6', 100: '#d5f2e8', 200: '#aee4d2', 500: '#2f9a7e', 600: '#237f67', 700: '#1f6655', 900: '#123c33' } },
    },
  },
  plugins: [],
}
