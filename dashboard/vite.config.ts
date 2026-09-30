import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Module 8: standard Vite dev server on port 5173 - matches the CORS allow_origins
// added to each of the 3 proxy services' main.py, so browser requests from this
// dashboard aren't blocked.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
  },
});
