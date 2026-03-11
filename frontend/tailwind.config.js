/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        brand: {
          50: "#FFFEF5",
          100: "#FFFDE0",
          200: "#FFF9B8",
          300: "#FFF285",
          400: "#FFEC52",
          500: "rgb(var(--brand-500) / <alpha-value>)",
          600: "#E6CE00",
          700: "#B39F00",
          800: "#807200",
          900: "#4D4400",
        },
        surface: {
          50: "rgb(var(--surface-50) / <alpha-value>)",
          100: "rgb(var(--surface-100) / <alpha-value>)",
          700: "rgb(var(--surface-700) / <alpha-value>)",
          800: "rgb(var(--surface-800) / <alpha-value>)",
          850: "rgb(var(--surface-850) / <alpha-value>)",
          900: "rgb(var(--surface-900) / <alpha-value>)",
          950: "rgb(var(--surface-950) / <alpha-value>)",
        },
        cream: "rgb(var(--color-cream) / <alpha-value>)",
        fg: {
          primary: "var(--fg-primary)",
          inverted: "var(--fg-inverted)",
        },
      },
      fontFamily: {
        display: ["Mondwest", "Arial", "sans-serif"],
        body: ["Inter", "Arial", "sans-serif"],
        mono: ["JetBrains Mono", "SF Mono", "monospace"],
      },
    },
  },
  plugins: [],
};
