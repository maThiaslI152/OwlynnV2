/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // Mode Themes
        normal: {
          surface: 'rgba(16, 30, 52, 0.25)',
          elevated: 'rgba(33, 60, 97, 0.35)',
          hover: 'rgba(67, 118, 186, 0.24)',
          borderSubtle: 'rgba(148, 196, 255, 0.10)',
          borderDefault: 'rgba(162, 208, 255, 0.20)',
          borderAccent: '#7bc5ff',
          accent: '#72c2ff',
          accentHover: '#8fd0ff',
          accentGlow: 'rgba(114, 194, 255, 0.2)',
          textPrimary: '#e8f5ff',
          textSecondary: '#b8d7f1',
          textMuted: '#86accb',
        },
        study: {
          surface: 'rgba(16, 42, 32, 0.35)',
          elevated: 'rgba(28, 77, 58, 0.45)',
          hover: 'rgba(45, 112, 85, 0.35)',
          borderSubtle: 'rgba(120, 255, 180, 0.15)',
          borderDefault: 'rgba(120, 255, 180, 0.25)',
          borderAccent: '#4ade80',
          accent: '#22c55e',
          accentHover: '#4ade80',
          accentGlow: 'rgba(34, 197, 94, 0.25)',
          textPrimary: '#e6fff0',
          textSecondary: '#a3e6c3',
          textMuted: '#72b392',
        },
        pentest: {
          surface: 'rgba(40, 10, 15, 0.35)',
          elevated: 'rgba(70, 15, 25, 0.45)',
          hover: 'rgba(110, 20, 35, 0.35)',
          borderSubtle: 'rgba(255, 80, 100, 0.15)',
          borderDefault: 'rgba(255, 80, 100, 0.25)',
          borderAccent: '#f43f5e',
          accent: '#e11d48',
          accentHover: '#f43f5e',
          accentGlow: 'rgba(225, 29, 72, 0.25)',
          textPrimary: '#ffe6eb',
          textSecondary: '#e6a3af',
          textMuted: '#b3727e',
        }
      },
      fontFamily: {
        sans: ['Outfit', '-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'Roboto', 'sans-serif'],
        mono: ['JetBrains Mono', 'Fira Code', 'Cascadia Code', 'monospace'],
      },
    },
  },
  plugins: [],
}
