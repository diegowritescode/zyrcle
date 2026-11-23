import path from "path";
import { defineConfig } from "vitest/config";

// Unit tests for the logic behind the pages (ADR 0031); the pages themselves run in e2e/.
export default defineConfig({
  resolve: { alias: { "@": path.resolve(__dirname, "./src") } },
  test: {
    include: ["src/**/*.test.ts"],
    environment: "node",
    coverage: { provider: "v8", include: ["src/lib/**", "src/console/**"], reporter: ["text-summary"] },
  },
});
