import { describe, expect, it } from "vitest";
import { ApiError, bookingErrorMessage, startErrorMessage } from "./api";

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
