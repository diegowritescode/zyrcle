import { defineConfig } from "vitest/config";

// Unit tests for the app's plain logic, with native modules replaced by stand-ins (ADR 0031). The
// screens run in e2e/ on the app's web export.
export default defineConfig({
  test: { include: ["src/**/*.test.ts"], environment: "node" },
});
