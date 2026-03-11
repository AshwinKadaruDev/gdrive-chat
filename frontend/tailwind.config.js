/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        brand: {
          50: "#FFFEF5",
          100: "#FFFDE0",
          200: "#FFF9B8",
          300: "#FFF285",
          400: "#FFEC52",
          500: "#FFE501",
          600: "#E6CE00",
          700: "#B39F00",
          800: "#807200",
          900: "#4D4400",
        },
        surface: {
          50: "#F0EEE5",
          100: "#AAAAAA",
          700: "#222222",
          800: "#1A1A1A",
          850: "#111111",
          900: "#0A0A0A",
          950: "#000000",
        },
        cream: "#F0EEE5",
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
