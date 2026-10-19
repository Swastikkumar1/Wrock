import { defineConfig } from "vite";

export default defineConfig({
  server: {
    port: 3000,
    strictPort: true,
    host: true,
  },
  build: {
    target: "esnext",
    outDir: "dist",
  },
});
