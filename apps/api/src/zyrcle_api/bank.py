"""Reading a bank statement and proposing what each movement pays (docs/adr/0039). Pure: no I/O.

The operator exports the statement from the bank's website (CSV or Excel) and uploads it. Columns
are found by their headers (fecha, descripción, referencia, valor, or separate crédito and débito),
so the parser does not depend on one bank's layout. Colombian numbers ("1.234.567,00") and the
usual date formats are understood.

Credits are proposed for sales waiting for their bank match: the same amount, within a few days of
the sale, scoring higher when the description carries the ticket number or the buyer's name. Debits
are proposed for redemptions waiting for their transfer, the same way, with the merchant's name or
tax id. A person confirms every match.
"""

import csv
import hashlib
import io
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

MAX_ROWS = 5_000
SALE_WINDOW_BEFORE = timedelta(days=1)
SALE_WINDOW_AFTER = timedelta(days=10)
REDEMPTION_WINDOW_AFTER = timedelta(days=10)

HEADERS = {
    "date": ("fecha", "date", "fecha movimiento", "fecha de movimiento", "fecha valor"),
    "description": ("descripcion", "description", "concepto", "detalle", "transaccion"),
    "reference": ("referencia", "reference", "documento", "dcto", "dcto.", "comprobante", "ref"),
    "amount": ("valor", "monto", "importe", "amount", "valor movimiento"),
    "credit": ("credito", "creditos", "abono", "abonos", "credit", "ingresos"),
    "debit": ("debito", "debitos", "cargo", "cargos", "debit", "egresos", "retiros"),
}
DATE_FORMATS = ("%d/%m/%Y", "%Y-%m-%d", "%Y/%m/%d", "%d-%m-%Y", "%d/%m/%y", "%Y%m%d", "%d.%m.%Y")


class StatementUnreadable(Exception):
    """The file is not a statement we can read; the message says what to do."""


@dataclass(frozen=True)
class BankRow:
    posted_on: date
    description: str
    reference: str
    amount_cop: int  # credits positive, debits negative

    def fingerprint(self, occurrence: int = 0) -> str:
        """The same movement in two statements gives the same fingerprint. `occurrence` tells apart
        identical movements on the same day in one statement."""
        parts = (self.posted_on, self.amount_cop, self.reference, self.description, occurrence)
        return hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()


def _plain(text: str) -> str:
    """Lowercase, without accents or extra spaces: how headers and names are compared."""
    nfkd = unicodedata.normalize("NFKD", str(text))
    return " ".join("".join(c for c in nfkd if not unicodedata.combining(c)).lower().split())


def parse_amount(value: Any) -> int | None:
    """Whole pesos from a cell: numbers, "1.234.567,00", "-20,000.00", "$ 20.000", "(1.500)"."""
    if value is None or value == "":
        return None
    if isinstance(value, int | float):
        return int(value)
    text = str(value).strip()
    negative = text.startswith("(") and text.endswith(")") or "-" in text
    digits = re.sub(r"[^0-9.,]", "", text)
    if not digits:
        return None
    if "." in digits and "," in digits:
        decimal = "." if digits.rfind(".") > digits.rfind(",") else ","
    elif digits.count(",") == 1 and len(digits.split(",")[1]) in (1, 2):
        decimal = ","
    elif digits.count(".") == 1 and len(digits.split(".")[1]) in (1, 2):
        decimal = "."
    else:
        decimal = None
    if decimal:
        whole = digits.rsplit(decimal, 1)[0]
    else:
        whole = digits
    pesos = int(re.sub(r"[.,]", "", whole) or 0)
    return -pesos if negative else pesos


def parse_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value or "").strip().split(" ")[0]
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _columns(header: list[Any]) -> dict[str, int] | None:
    names = [_plain(h or "") for h in header]
    found: dict[str, int] = {}
    for role, options in HEADERS.items():
        for i, name in enumerate(names):
            if name in options or any(name.startswith(o + " ") for o in options):
                found.setdefault(role, i)
    if "date" in found and ("amount" in found or "credit" in found or "debit" in found):
        return found
    return None


def _rows_from_table(table: list[list[Any]]) -> list[BankRow]:
    start, cols = next(
        ((i, c) for i, h in enumerate(table[:30]) if (c := _columns(h)) is not None), (-1, None)
    )
    if cols is None:
        raise StatementUnreadable(
            "no encontramos las columnas de fecha y valor: exporta el extracto con encabezados"
        )
    rows: list[BankRow] = []
    for raw in table[start + 1 : start + 1 + MAX_ROWS]:

        def cell(role: str, raw: list[Any] = raw) -> Any:
            i = cols.get(role)
            return raw[i] if i is not None and i < len(raw) else None

        posted = parse_date(cell("date"))
        if posted is None:
            continue  # totals, blank lines, page footers
        if "amount" in cols:
            amount = parse_amount(cell("amount"))
        else:
            credit, debit = parse_amount(cell("credit")) or 0, parse_amount(cell("debit")) or 0
            amount = credit - abs(debit)
        if not amount:
            continue
        rows.append(
            BankRow(
                posted_on=posted,
                description=str(cell("description") or "").strip()[:300],
                reference=str(cell("reference") or "").strip()[:100],
                amount_cop=amount,
            )
        )
    if not rows:
        raise StatementUnreadable("el extracto no tiene movimientos que entendamos")
    return rows


def parse_statement(filename: str, content: bytes) -> list[BankRow]:
    """The movements of a CSV or Excel (.xlsx) statement."""
    if filename.lower().endswith((".xlsx", ".xlsm")):
        from openpyxl import load_workbook

        try:
            sheet = load_workbook(io.BytesIO(content), read_only=True, data_only=True).active
        except Exception:
            raise StatementUnreadable("no pudimos abrir ese archivo de Excel") from None
        table = [list(r) for r in sheet.iter_rows(values_only=True)]  # type: ignore[union-attr]
        return _rows_from_table(table)
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = content.decode("latin-1")
    return _rows_from_table(list(csv.reader(io.StringIO(text), delimiter=_delimiter(text))))


def _delimiter(text: str) -> str:
    """The separator that splits most of the first lines into three or more columns. Banks put
    a title above the table, and Colombian amounts carry commas, which fools csv.Sniffer."""
    lines = text.splitlines()[:40]

    def fits(sep: str) -> int:
        return sum(len(row) >= 3 for row in csv.reader(lines, delimiter=sep))

    return max([";", "\t", "|", ","], key=fits)


# ---------------------------------------------------------------- proposals


@dataclass
class Proposal:
    line_id: str
    kind: str  # "sale" | "redemption"
    target_id: str
    score: int
    why: list[str] = field(default_factory=list)


def _mentions(text: str, needle: str | None) -> bool:
    if not needle:
        return False
    hay, n = _plain(text), _plain(needle)
    return bool(n) and (n in hay or n.replace("-", "") in hay.replace("-", ""))


def _words(text: str | None) -> set[str]:
    return {w for w in re.split(r"[^a-z0-9]+", _plain(text or "")) if len(w) >= 4}


def propose(
    lines: list[dict[str, Any]], sales: list[dict[str, Any]], redemptions: list[dict[str, Any]]
) -> list[Proposal]:
    """Best match for each sale and redemption, each line used once, best scores first.

    lines: [{id, posted_on: date, description, reference, amount_cop}] not matched yet
    sales: [{id, total_cop, sold_on: date, ticket_ref, buyer}] waiting for their bank match
    redemptions: [{id, amount_cop, requested_on: date, merchant, tax_id}] waiting for transfer
    """
    candidates: list[Proposal] = []
    for s in sales:
        for line in lines:
            if line["amount_cop"] != s["total_cop"]:
                continue
            days = (line["posted_on"] - s["sold_on"]).days
            if not -SALE_WINDOW_BEFORE.days <= days <= SALE_WINDOW_AFTER.days:
                continue
            text = f"{line['description']} {line['reference']}"
            why, score = ["mismo valor"], 60 + max(0, 20 - 2 * abs(days))
            if _mentions(text, s.get("ticket_ref")):
                score, why = score + 15, [*why, "nombra el tiquete"]
            if _words(s.get("buyer")) & _words(text):
                score, why = score + 5, [*why, "nombra al comprador"]
            candidates.append(Proposal(str(line["id"]), "sale", str(s["id"]), score, why))
    for r in redemptions:
        for line in lines:
            if line["amount_cop"] != -r["amount_cop"]:
                continue
            days = (line["posted_on"] - r["requested_on"]).days
            if not 0 <= days <= REDEMPTION_WINDOW_AFTER.days:
                continue
            text = f"{line['description']} {line['reference']}"
            why, score = ["mismo valor"], 60 + max(0, 20 - 2 * days)
            if _mentions(text, r.get("tax_id")):
                score, why = score + 15, [*why, "nombra el NIT"]
            if _words(r.get("merchant")) & _words(text):
                score, why = score + 10, [*why, "nombra al comercio"]
            candidates.append(Proposal(str(line["id"]), "redemption", str(r["id"]), score, why))
    chosen: list[Proposal] = []
    used_lines: set[str] = set()
    used_targets: set[tuple[str, str]] = set()
    for p in sorted(candidates, key=lambda p: -p.score):
        if p.line_id in used_lines or (p.kind, p.target_id) in used_targets:
            continue
        chosen.append(p)
        used_lines.add(p.line_id)
        used_targets.add((p.kind, p.target_id))
    return chosen
