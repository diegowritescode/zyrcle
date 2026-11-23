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
    """The container's site is closed at this hour."""

    code = "closed"


class SlotFull(Conflict):
    """Every spot of the hour is taken (booked or walk-in)."""

    code = "slot_full"


class AlreadyBooked(Conflict):
    code = "already_booked"


class TooManyBookings(Conflict):
    code = "too_many_bookings"


class RateLimited(SessionError):
    status, code = 429, "rate_limited"


class TooSoon(RateLimited):
    """A code was sent less than a minute ago."""

    code = "too_soon"


class TooManyCodes(RateLimited):
    code = "too_many_codes"


class CodeInvalid(Invalid):
    """Wrong, expired, already used or never requested."""

    code = "code_invalid"


class EmailTaken(Conflict):
    code = "email_taken"


class PhoneInUse(Conflict):
    """The phone asking to recover an account already has deposits or turns of its own."""

    code = "phone_in_use"


class RecoveryPending(Conflict):
    """This phone is waiting for an account; it cannot deposit or book until then."""

    code = "recovery_pending"


class RecoveryUnavailable(Unavailable):
    code = "recovery_unavailable"


class InvalidEmail(Invalid):
    code = "invalid_email"


class RecoveryInProgress(Conflict):
    """This phone is already waiting for another account."""

    code = "recovery_in_progress"


class ConsentRequired(Forbidden):
    """The participant has not accepted the data-processing policy in force (docs/adr/0028)."""

    code = "consent_required"
