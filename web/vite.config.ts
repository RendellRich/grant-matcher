import { defineConfig } from "vite";
import preact from "@preact/preset-vite";

// GitHub Pages serves the site from /grant-matcher/; BASE overrides it for other hosts.
export default defineConfig({
  base: process.env.BASE ?? "/grant-matcher/",
  plugins: [preact()],
  worker: { format: "es" },
  build: { target: "es2022", chunkSizeWarningLimit: 1200 },
  test: { include: ["test/**/*.test.ts"] },
} as never);
