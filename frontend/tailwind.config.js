/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        ironlayer: {
          50: '#eef6ff',
          100: '#d9ebff',
          200: '#bcdbff',
          300: '#8ec4ff',
          400: '#59a3ff',
          500: '#3381ff',
          600: '#1a5ff5',
          700: '#1349e1',
          800: '#163cb6',
          900: '#18378f',
          950: '#0f1f4d',
        },
        surface: {
          DEFAULT: '#0a0a0f',
          50: '#16161e',
          100: '#1c1c28',
          200: '#24243a',
          300: '#2e2e4a',
          400: '#3a3a5c',
        },
        accent: {
          cyan: '#06d6a0',
          purple: '#8b5cf6',
          orange: '#f59e0b',
          pink: '#ec4899',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'sans-serif'],
        mono: ['JetBrains Mono', 'Fira Code', 'monospace'],
      },
    },
  },
  plugins: [],
};
