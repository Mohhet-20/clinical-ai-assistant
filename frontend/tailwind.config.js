/** @type {import('tailwindcss').Config} */
const steps = [50, 100, 200, 300, 400, 500, 600, 700, 800, 900]
// Every scale reads a CSS variable (src/theme.css), so dark mode is one class on <html> instead of a dark: variant per utility.
const scale = name => Object.fromEntries(steps.map(s => [s, `rgb(var(--${name}-${s}) / <alpha-value>)`]))

export default {
  darkMode: 'class',
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      fontFamily: { sans: ['"DM Sans"', 'ui-sans-serif', 'system-ui', 'sans-serif'], mono: ['"DM Mono"', 'ui-monospace', 'monospace'] },
      colors: {
        slate: scale('slate'), red: scale('red'), amber: scale('amber'), emerald: scale('emerald'), sky: scale('sky'),
        orange: scale('orange'), violet: scale('violet'), brand: scale('brand'),
        surface: 'rgb(var(--surface) / <alpha-value>)', canvas: 'rgb(var(--canvas) / <alpha-value>)',
        action: 'rgb(var(--action) / <alpha-value>)',   // fill behind white text; AA in both themes
        // status palette (dataviz reference): always paired with a text label, never colour alone
        status: { good: '#0ca30c', warning: '#fab219', serious: '#ec835a', critical: '#d03b3b' },
        series: { symptom: '#2a78d6', condition: '#eb6834', medication: '#1baf7a', risk: '#6250d6' },
      },
      boxShadow: {
        card: '0 1px 2px rgb(15 23 42 / 0.04), 0 4px 16px -4px rgb(15 23 42 / 0.06)',
        lift: '0 2px 4px rgb(15 23 42 / 0.05), 0 12px 32px -8px rgb(15 23 42 / 0.14)',
      },
      keyframes: {
        'fade-up': { from: { opacity: '0', transform: 'translateY(6px)' }, to: { opacity: '1', transform: 'none' } },
        shimmer: { from: { backgroundPosition: '200% 0' }, to: { backgroundPosition: '-200% 0' } },
      },
      animation: { 'fade-up': 'fade-up .35s ease-out both', shimmer: 'shimmer 1.6s linear infinite' },
    },
  },
  plugins: [],
}
