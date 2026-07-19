import { defineConfig } from "vitest/config";
import vue from "@vitejs/plugin-vue";

export default defineConfig({
  plugins: [vue()],
  test: {
    environment: "happy-dom",
  },
  server: {
    port: 5173,
    proxy: { "/api": "http://127.0.0.1:7331" },
  },
  build: {
    outDir: "../src/asksql/studio/static",
    emptyOutDir: true,
  },
});
