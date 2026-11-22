import { defineConfig } from "vite";
import react from "@vitejs/plugin-react-swc";
import path from "path";

// https://vitejs.dev/config/
export default defineConfig({
  server: {
    host: "::",
    port: 8080,
  },
  plugins: [react()],
  // The entry chunk carries viem (wallet + SIWE signing), needed from the first page; routes are
  // split in App.tsx.
  build: { chunkSizeWarningLimit: 800 },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
});
