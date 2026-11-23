# ADR 0038: Reading the scale ticket from a photo with Claude, and a person confirms

- Status: proposed (2026-11-23)
- Decided by: Claude, building block 3 (M15) under ADR 0030, which Diego confirmed. Not yet
  confirmed. Needs Diego's Anthropic API key.

## Context
Every sale starts from the collection center's scale ticket (ADR 0013). The operator typed it by
hand: center, number, date, and per material the kilograms, the price and the amount, then matched
each line to a bag. That is slow, and a typo moves money.

## Decision
- **The operator photographs the ticket in the console.** The browser shrinks it to at most 1600
  pixels and sends it as JPEG.
- **Claude reads it into a fixed shape** with structured output (`output_config.format`, a JSON
  schema): readable or not, center, ticket number, date, lines (material from Zyrcle's list or
  "other", the ticket's own label, kilograms, price per kilogram, amount) and total. The prompt
  explains Colombian number formats and the material names, and asks for null rather than a guess.
  Model `claude-opus-5-5` through the official Python SDK, with the server-side refusal fallback
  (`fallbacks: "default"`). About US$0.03 per ticket.
- **The API checks and proposes, it never decides.** It flags kilograms times price that do not give
  the amount, lines that do not add to the total, missing numbers or dates, and unknown materials;
  it proposes for each line the sealed bag of that material closest in weight, each bag once; it
  matches the center by name. The console fills the sale form with all of it, and the operator
  reviews and corrects before recording the sale. Nothing is recorded without a person.
- **Everything is kept for audit:** the photo, its hash, the model and request id, the reading, who
  sent it, and the sale it became (`ticket_scan`). A failed reading keeps the photo and says why.
- **Off without a key**, like every external service in block 3.

## Consequences
- Recording a sale becomes taking a photo, checking, and pressing a button.
- Photos of tickets reach Anthropic; they show the center's ticket, not participants.
- A misread number is still possible; the checks catch arithmetic, not a consistently wrong digit,
  which is why a person confirms and the bank match still follows (ADR 0013).
- Tested with a stand-in of the API that checks the request (model, image, schema, fallback): in the
  backend suite and in the end-to-end journey, where the day's sale now starts from a photo.
