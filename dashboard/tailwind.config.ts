import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        "node-file": "#3B82F6",
        "node-symbol": "#06B6D4",
        "node-commit": "#22C55E",
        "node-pr": "#F97316",
        "node-issue": "#EAB308",
        "node-discussion": "#EC4899",
        "node-decision": "#F59E0B",
        "node-person": "#FFFFFF",
      },
    },
  },
  plugins: [],
};

export default config;
