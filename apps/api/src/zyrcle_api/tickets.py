"""Reading a collection center's scale ticket from a photo (docs/adr/0038).

The operator photographs the ticket; Claude reads it into a fixed JSON shape (structured output):
center, ticket number, date, and per material the kilograms, price per kilogram and amount, plus the
total. The API then checks the arithmetic and proposes which sealed bag each line is, and the
operator reviews and corrects everything before a sale is recorded. Nothing is saved as a sale
without a person.
"""

import json
from dataclasses import dataclass
from datetime import date
from typing import Any

from pydantic import BaseModel, ValidationError

from .sessions import MATERIALS

MODEL = "claude-opus-5-5"
OTHER = "other"
# A line's amount may differ from kilograms x price by rounding on the ticket.
AMOUNT_TOLERANCE = 0.01
AMOUNT_TOLERANCE_COP = 100

SYSTEM = f"""You read photos of scale tickets ("tiquetes de báscula") from recycling collection
centers in Colombia and return what the ticket says, nothing more.

- Colombian numbers use "." for thousands and "," for decimals: "1.250,5 kg" is 1250.5 kg and
  "$ 3.200" is 3200 pesos. Return plain numbers.
- Map each line's material to one of {", ".join(MATERIALS)} or "{OTHER}": pet (PET, botellas
  plásticas transparentes), hdpe (PEAD, soplado, plástico de envases opacos), metal (aluminio,
  latas, chatarra), glass (vidrio), cardboard (cartón), paper (archivo, papel). Keep the ticket's
  own wording in "label".
- Weights in kilograms, prices in pesos per kilogram, amounts and the total in pesos.
- Use null for anything you cannot read with confidence. Never guess a number.
- If the photo is not a scale ticket or cannot be read, set "readable" to false and say why in
  "notes"."""

SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "readable": {"type": "boolean"},
        "center_name": {"type": ["string", "null"]},
        "ticket_ref": {"type": ["string", "null"]},
        "date": {"type": ["string", "null"], "description": "YYYY-MM-DD"},
        "lines": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "material": {"type": "string", "enum": [*MATERIALS, OTHER]},
                    "label": {"type": "string"},
                    "kg": {"type": ["number", "null"]},
                    "cop_per_kg": {"type": ["number", "null"]},
                    "amount_cop": {"type": ["number", "null"]},
                },
                "required": ["material", "label", "kg", "cop_per_kg", "amount_cop"],
                "additionalProperties": False,
            },
        },
        "total_cop": {"type": ["number", "null"]},
        "notes": {"type": "string"},
    },
    "required": ["readable", "center_name", "ticket_ref", "date", "lines", "total_cop", "notes"],
    "additionalProperties": False,
}


class TicketLine(BaseModel):
    material: str
    label: str
    kg: float | None
    cop_per_kg: float | None
    amount_cop: float | None


class TicketRead(BaseModel):
    readable: bool
    center_name: str | None
    ticket_ref: str | None
    date: str | None
    lines: list[TicketLine]
    total_cop: float | None
    notes: str


class TicketUnreadable(Exception):
    """The model did not return a reading (it declined, or the answer did not fit the schema)."""


@dataclass(frozen=True)
class Reading:
    read: TicketRead
    model: str
    request_id: str | None


class ClaudeTicketReader:
    """Reads a ticket with the Anthropic API. `client` is an `anthropic.AsyncAnthropic`."""

    def __init__(self, client, model: str = MODEL):
        self._client = client
        self._model = model

    async def read(self, image_b64: str, media_type: str) -> Reading:
        response = await self._client.beta.messages.create(
            model=self._model,
            max_tokens=16_000,
            system=SYSTEM,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": image_b64,
                            },
                        },
                        {"type": "text", "text": "Lee este tiquete."},
                    ],
                }
            ],
            output_config={"effort": "medium", "format": {"type": "json_schema", "schema": SCHEMA}},
            # On a safety decline the API re-runs the request on its recommended fallback model.
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
        if response.stop_reason == "refusal":
            raise TicketUnreadable("the model declined to read this image")
        text = next((b.text for b in response.content if b.type == "text"), "")
        try:
            read = TicketRead.model_validate(json.loads(text))
        except (ValueError, ValidationError) as e:
            raise TicketUnreadable(f"the reading did not fit the expected shape: {e}") from None
        return Reading(read, response.model, getattr(response, "_request_id", None))


def checks(read: TicketRead) -> list[dict[str, Any]]:
    """What the operator should look at: arithmetic that does not add up, unknown materials,
    a missing number, date or ticket number."""
    found: list[dict[str, Any]] = []

    def note(kind: str, detail: str, line: int | None = None) -> None:
        found.append({"kind": kind, "detail": detail, **({} if line is None else {"line": line})})

    if not read.readable:
        note("unreadable", read.notes or "no se pudo leer")
    if not read.ticket_ref:
        note("missing", "falta el número del tiquete")
    try:
        date.fromisoformat(read.date or "")
    except ValueError:
        note("missing", "falta la fecha o no se entiende")
    for i, line in enumerate(read.lines):
        if line.material == OTHER:
            note("material", f"material sin clasificar: {line.label}", i)
        if line.kg is None or line.amount_cop is None:
            note("missing", f"faltan kilos o valor en {line.label}", i)
        elif line.cop_per_kg is not None:
            expected = line.kg * line.cop_per_kg
            slack = max(AMOUNT_TOLERANCE * expected, AMOUNT_TOLERANCE_COP)
            if abs(expected - line.amount_cop) > slack:
                detail = f"{line.label}: {line.kg} kg x {line.cop_per_kg} no da {line.amount_cop}"
                note("arithmetic", detail, i)
    amounts = [line.amount_cop for line in read.lines if line.amount_cop is not None]
    total = read.total_cop
    if total is not None and amounts and abs(sum(amounts) - total) > AMOUNT_TOLERANCE_COP:
        note("arithmetic", f"las líneas suman {sum(amounts):,.0f}, el total dice {total:,.0f}")
    return found


def propose_bags(read: TicketRead, sealed: list[dict[str, Any]]) -> list[str | None]:
    """For each line, the sealed bag of the same material whose weight is closest to the line's,
    each bag used once. `sealed`: [{"code", "material", "grams"}]."""
    free = list(sealed)
    proposals: list[str | None] = []
    for line in read.lines:
        candidates = [b for b in free if b["material"] == line.material]
        if not candidates or line.kg is None:
            proposals.append(None)
            continue
        target = line.kg * 1_000
        best = min(candidates, key=lambda b: abs(b["grams"] - target))
        free.remove(best)
        proposals.append(best["code"])
    return proposals
