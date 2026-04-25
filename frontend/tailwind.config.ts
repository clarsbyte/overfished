import type { Config } from "tailwindcss";
import animate from "tailwindcss-animate";

export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Dark control-room palette from PRD §4.2
        ink: {
          950: "#0a0e1a",
          900: "#11172a",
          800: "#1a2138",
          700: "#1f2740",
        },
        slate2: {
          200: "#e8ecf5",
          400: "#7a8398",
        },
        accent: {
          safe: "#00d4ff",
          suspect: "#ffaa00",
          iuu: "#ff3b3b",
        },
      },
      fontFamily: {
        mono: ["JetBrains Mono", "ui-monospace", "monospace"],
        display: ["Space Grotesk", "Geist Sans", "system-ui", "sans-serif"],
      },
    },
  },
  plugins: [animate],
} satisfies Config;
