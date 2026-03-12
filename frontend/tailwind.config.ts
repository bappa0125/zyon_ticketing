import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/config/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        ai: {
          bg: "var(--ai-bg)",
          surface: "var(--ai-surface)",
          border: "var(--ai-border)",
          text: "var(--ai-text)",
          muted: "var(--ai-muted)",
          accent: "var(--ai-accent)",
        },
      },
      maxWidth: {
        content: "var(--ai-max-content)",
      },
      fontFamily: {
        sans: ["var(--font-sans)", "system-ui", "sans-serif"],
      },
      animation: {
        "fade-in": "ai-fade-in 0.4s ease-out forwards",
        "slide-in": "ai-slide-in-right 0.35s ease-out forwards",
      },
    },
  },
  plugins: [],
};
export default config;
