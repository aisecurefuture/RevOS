import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        brand: {
          DEFAULT: "#4f46e5", // indigo-600
          dark: "#4338ca",
          light: "#6366f1",
        },
      },
    },
  },
  plugins: [],
};

export default config;
