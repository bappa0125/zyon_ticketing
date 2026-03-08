import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        surface: "#0f0f0f",
        surfaceHover: "#1a1a1a",
        border: "#2a2a2a",
        text: "#ededed",
        muted: "#a0a0a0",
      },
    },
  },
  plugins: [],
};
export default config;
