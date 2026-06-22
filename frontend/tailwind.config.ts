import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        hive: {
          50: "#f0f7ff",
          100: "#e0effe",
          200: "#b9dffb",
          300: "#7cc5f8",
          400: "#36a9f2",
          500: "#0c8ee2",
          600: "#0071c6",
          700: "#015a9f",
          800: "#064c83",
          900: "#0b406d",
          950: "#07284a",
        },
      },
    },
  },
  plugins: [],
};

export default config;
