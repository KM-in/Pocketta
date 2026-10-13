import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

// Keep browser requests on the frontend origin, including Vite's fallback ports.
// The backend still binds to loopback and retains its restricted CORS policy.
const proxy = { "/api": { target: "http://127.0.0.1:8000", changeOrigin: true } };

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    setupFiles: "./src/test/setup.ts",
  },
  server: {
    host: "127.0.0.1",
    port: 5173,
    proxy,
  },
  preview: { host: "127.0.0.1", proxy },
});
