import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The central portal is a plain web app served by any static host.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5174,
    strictPort: true,
    host: "127.0.0.1",
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
    target: "es2021",
  },
});
