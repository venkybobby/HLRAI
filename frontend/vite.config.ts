import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// /api is proxied to the FastAPI service so the browser sees one origin (cookies, CSRF later).
export default defineConfig({
  plugins: [react()],
  server: { port: 5173, proxy: { "/api": process.env.HLRAI_API ?? "http://127.0.0.1:8000" } },
  preview: { port: 5173, proxy: { "/api": process.env.HLRAI_API ?? "http://127.0.0.1:8000" } },
});
