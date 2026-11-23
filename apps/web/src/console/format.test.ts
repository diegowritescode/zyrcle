import { describe, expect, it, vi } from "vitest";

vi.mock("sonner", () => ({ toast: { error: vi.fn() } }));
const { signedGrams } = await import("./format");

describe("console formatting", () => {
    it("signs grams when they are a difference", () => {
        expect(signedGrams(1500)).toBe("+1.500 g");
        expect(signedGrams(-20)).toBe("-20 g");
        expect(signedGrams(0)).toBe("0 g");
    });
});
