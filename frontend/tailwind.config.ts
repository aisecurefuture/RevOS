import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        brand: {
          DEFAULT: "#7c3aed", // violet-600
          dark: "#6d28d9", // violet-700
          light: "#8b5cf6", // violet-500
        },
      },
    },
  },
  plugins: [],
};

export default config;
