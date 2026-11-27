import { describe, expect, it } from "vitest";
import { accountErrorMessage, ApiError, bookingErrorMessage, createApi, startErrorMessage } from "./api";

describe("error messages", () => {
  it("explains a closed container with its hours", () => {
    const e = new ApiError(409, "the container is open from 06:00 to 22:00", "closed");
    expect(startErrorMessage(e)).toBe("El contenedor está cerrado a esta hora. Abre de 6:00 a. m. a 10:00 p. m.");
    expect(bookingErrorMessage(e)).toBe("A esa hora está cerrado. Abre de 6:00 a. m. a 10:00 p. m.");
    const late = new ApiError(409, "the container is open from 03:00 to 24:00", "closed");
    expect(startErrorMessage(late)).toBe("El contenedor está cerrado a esta hora. Abre de 3:00 a. m. a medianoche.");
  });

  it("tells a resident without a spot what to do", () => {
    const e = new ApiError(409, "every spot of this hour is booked", "slot_full");
    expect(startErrorMessage(e)).toMatch(/Reserva otra hora/);
    expect(bookingErrorMessage(e)).toBe("Esa hora se acaba de llenar. Elige otra.");
  });

  it("covers the booking limits", () => {
    expect(bookingErrorMessage(new ApiError(409, "x", "too_many_bookings"))).toMatch(/hasta 3/);
    expect(bookingErrorMessage(new ApiError(422, "that hour is over", "invalid"))).toBe("Esa hora ya pasó.");
  });
});

describe("account error messages", () => {
  it("counts the attempts left on a wrong code", () => {
    expect(accountErrorMessage(new ApiError(422, "wrong code, 3 attempts left", "code_invalid"))).toBe(
      "El código no es correcto. Te quedan 3 intentos.",
    );
    expect(accountErrorMessage(new ApiError(422, "wrong code, 1 attempts left", "code_invalid"))).toBe(
      "El código no es correcto. Te quedan 1 intento.",
    );
    expect(accountErrorMessage(new ApiError(422, "wrong code, 0 attempts left", "code_invalid"))).toBe(
      "Ese código ya no sirve. Pide uno nuevo.",
    );
    expect(accountErrorMessage(new ApiError(422, "the code expired or was never requested", "code_invalid"))).toBe(
      "El código no es válido o ya venció. Pide uno nuevo.",
    );
  });

  it("says how long to wait for another code", () => {
    const e = new ApiError(429, "wait 42 seconds before asking for another code", "too_soon");
    expect(accountErrorMessage(e)).toBe("Espera 42 segundos para pedir otro código.");
  });

  it("explains why a phone waiting for an account cannot deposit or book", () => {
    const e = new ApiError(409, "this phone is waiting to recover an account", "recovery_pending");
    expect(startErrorMessage(e)).toMatch(/esperando tu cuenta anterior/);
    expect(bookingErrorMessage(e)).toMatch(/esperando tu cuenta anterior/);
  });
});

describe("start errors while a container is busy", () => {
  it("speaks Spanish when it is being emptied or another deposit is open", () => {
    expect(startErrorMessage(new ApiError(409, "this container is being emptied; try again in a few minutes", "conflict"))).toBe(
      "Están vaciando este contenedor. Intenta en unos minutos.",
    );
    expect(startErrorMessage(new ApiError(409, "you already have an open session", "conflict"))).toBe(
      "Ya tienes un depósito abierto. Termínalo antes de abrir otro.",
    );
  });
});


describe("rate limits", () => {
  it("are said in plain Spanish, whatever the screen", async () => {
    const { createApi, startErrorMessage, paymentErrorMessage, TOO_FAST } = await import("./api");
    const original = globalThis.fetch;
    globalThis.fetch = (async () =>
      new Response(JSON.stringify({ detail: { code: "rate_limited", detail: "too many requests; try again in 3 seconds" } }), { status: 429 })) as typeof fetch;
    try {
      const err = await createApi("http://x").api.stats().catch((e: unknown) => e);
      expect(startErrorMessage(err)).toBe(TOO_FAST);
      expect(paymentErrorMessage(err)).toBe(TOO_FAST);
    } finally {
      globalThis.fetch = original;
    }
  });
});

describe("merchantExport", () => {
  const respond = (body: BodyInit, answer: ResponseInit) => {
    const calls: { url: string; init?: RequestInit }[] = [];
    globalThis.fetch = (async (url: string, init?: RequestInit) => {
      calls.push({ url, init });
      return new Response(body, answer);
    }) as typeof fetch;
    return calls;
  };

  it("downloads the bytes with the name the API gave the file", async () => {
    const calls = respond("﻿Fecha\r\n", {
      headers: {
        "Content-Type": "text/csv; charset=utf-8",
        "Content-Disposition": 'attachment; filename="zyrcle-cafe-2026-11-01-a-2026-11-30.csv"',
      },
    });
    const { api } = createApi("https://api.test");
    const file = await api.merchantExport("tok", { start: "2026-11-01", end: "2026-11-30" }, "csv");
    expect(calls[0].url).toBe("https://api.test/v1/merchant/export?start=2026-11-01&end=2026-11-30&format=csv");
    expect(calls[0].init?.headers).toEqual({ Authorization: "Bearer tok" });
    expect(file.name).toBe("zyrcle-cafe-2026-11-01-a-2026-11-30.csv");
    expect(file.type).toBe("text/csv; charset=utf-8");
    // The byte order mark arrives too (a plain TextDecoder would drop it from the text).
    expect(new TextDecoder("utf-8", { ignoreBOM: true }).decode(file.bytes)).toBe("﻿Fecha\r\n");
  });

  it("turns the API's refusal into an ApiError", async () => {
    respond(JSON.stringify({ detail: { code: "forbidden", detail: "only merchants can do this" } }), { status: 403 });
    const { api } = createApi("https://api.test");
    await expect(api.merchantExport("tok", { start: "2026-11-01", end: "2026-11-30" }, "xlsx")).rejects.toMatchObject({
      status: 403,
      code: "forbidden",
      message: "only merchants can do this",
    });
  });
});
