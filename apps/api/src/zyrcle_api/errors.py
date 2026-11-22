"""Errors the services raise and the API turns into HTTP responses ({"code", "detail"})."""


class SessionError(Exception):
    status = 400
    code = "bad_request"

    def __init__(self, detail: str):
        super().__init__(detail)
        self.detail = detail


class NotFound(SessionError):
    status, code = 404, "not_found"


class Forbidden(SessionError):
    status, code = 403, "forbidden"


class Conflict(SessionError):
    status, code = 409, "conflict"


class Invalid(SessionError):
    status, code = 422, "invalid"


class Unavailable(SessionError):
    status, code = 503, "unavailable"


class Closed(Conflict):
    """The container's residence is closed at this hour."""

    code = "closed"


class SlotFull(Conflict):
    """Every spot of the hour is taken (booked or walk-in)."""

    code = "slot_full"


class AlreadyBooked(Conflict):
    code = "already_booked"


class TooManyBookings(Conflict):
    code = "too_many_bookings"
