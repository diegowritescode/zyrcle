"""An impact certificate as a formal PDF (docs/adr/0046): what the monthly report emails to a
host, and what `GET /v1/certificates/{id}/pdf` returns. One A4 page: the figures, the table by
material, how they were counted, and how to verify them, with a QR to the public verification page.

The PDF only presents the certificate. What proves it is the Merkle root anchored on ZyrcleChain
and the public copy on IPFS, which the verification page checks in the reader's browser.
"""

import io
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from reportlab.graphics import renderPDF
from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen.canvas import Canvas

from .filenames import slug

MATERIALS = {
    "pet": "PET",
    "hdpe": "HDPE",
    "metal": "Latas",
    "glass": "Vidrio",
    "paper": "Papel",
    "cardboard": "Cartón",
}
MONTHS = (
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
)
FOREST = HexColor("#064E3B")
EMERALD = HexColor("#10B981")
MUTED = HexColor("#64748B")
LINE = HexColor("#E2E8F0")


def month_name(period: str) -> str:
    """'2026-11' as 'noviembre de 2026'."""
    year, month = period.split("-")
    return f"{MONTHS[int(month) - 1]} de {year}"


def kg(grams: int) -> str:
    """Kilograms the Colombian way: a dot for thousands, a comma for decimals."""
    text = f"{grams / 1000:,.1f}"
    return text.replace(",", "_").replace(".", ",").replace("_", ".") + " kg"


def verify_url(web_url: str, certificate_id: str) -> str:
    return f"{web_url.rstrip('/')}/certificates/{certificate_id}"


def pdf_filename(certificate: dict[str, Any]) -> str:
    name = certificate["host"]["name"]
    if certificate.get("site"):
        name += " " + certificate["site"]["name"]
    return f"zyrcle-certificado-{slug(name, 'institucion', 60)}-{certificate['period']}.pdf"


def _wrap(canvas: Canvas, text: str, font: str, size: float, width: float) -> list[str]:
    lines: list[str] = []
    for paragraph in text.split("\n"):
        line = ""
        for word in paragraph.split(" "):
            candidate = f"{line} {word}".strip()
            if canvas.stringWidth(candidate, font, size) <= width or not line:
                line = candidate
            else:
                lines.append(line)
                line = word
        lines.append(line)
    return lines


def render_certificate(
    certificate: dict[str, Any], web_url: str, chain_id: int, tz: ZoneInfo, now: datetime
) -> bytes:
    """`certificate` is the API's view of it (`impact.certificate_view`)."""
    out = io.BytesIO()
    page = Canvas(out, pagesize=A4, pageCompression=1)
    page.setTitle(
        f"Certificado de impacto · {certificate['host']['name']} · {certificate['period']}"
    )
    page.setAuthor("Zyrcle")
    page.setSubject("Material recuperado y vendido a un reciclador, y CO2e evitado")
    width, height = A4
    left, right = 20 * mm, width - 20 * mm
    y = height - 22 * mm

    def text(x: float, y: float, value: str, size: float = 10, font="Helvetica", color=FOREST):
        page.setFont(font, size)
        page.setFillColor(color)
        page.drawString(x, y, value)

    def paragraph(y: float, value: str, size: float = 8.5, color=MUTED, width=right - left):
        for line in _wrap(page, value, "Helvetica", size, width):
            text(left, y, line, size, color=color)
            y -= size * 1.45
        return y

    text(left, y, "Zyrcle", 14, "Helvetica-Bold", EMERALD)
    text(right - 62 * mm, y, f"Certificado {certificate['id'][:8]}", 9, color=MUTED)
    y -= 14 * mm
    text(left, y, "Certificado de impacto", 22, "Helvetica-Bold")
    y -= 9 * mm
    place = certificate["host"]["name"]
    if certificate.get("site"):
        place += f" · {certificate['site']['name']}"
    text(left, y, place, 13, "Helvetica-Bold")
    y -= 6.5 * mm
    text(left, y, f"Material vendido en {month_name(certificate['period'])}", 11, color=MUTED)

    # The three figures.
    y -= 16 * mm
    box_w = (right - left - 8 * mm) / 3
    figures = [
        ("Material recuperado y vendido", kg(certificate["grams"]), "a un reciclador"),
        ("CO2e evitado", kg(certificate["co2e_g"]), "frente al relleno sanitario"),
        (
            "Depósitos verificados",
            f"{certificate['deposits']:,}".replace(",", "."),
            f"de {certificate['participants']} "
            + ("persona" if certificate["participants"] == 1 else "personas"),
        ),
    ]
    for i, (label, value, note) in enumerate(figures):
        x = left + i * (box_w + 4 * mm)
        page.setFillColor(HexColor("#ECFDF5") if i != 1 else EMERALD)
        page.roundRect(x, y - 14 * mm, box_w, 24 * mm, 3 * mm, stroke=0, fill=1)
        ink = FOREST if i != 1 else HexColor("#FFFFFF")
        text(x + 4 * mm, y + 4 * mm, label, 8.5, color=ink)
        text(x + 4 * mm, y - 4 * mm, value, 17, "Helvetica-Bold", ink)
        text(x + 4 * mm, y - 10 * mm, note, 8, color=ink)

    # By material.
    y -= 30 * mm
    text(left, y, "Por material", 11, "Helvetica-Bold")
    y -= 7 * mm
    columns = (left, left + 80 * mm, left + 125 * mm)
    for x, head in zip(columns, ("Material", "Recuperado", "CO2e evitado"), strict=True):
        text(x, y, head, 8.5, "Helvetica-Bold", MUTED)
    y -= 2.5 * mm
    page.setStrokeColor(LINE)
    page.line(left, y, right, y)
    for material, row in certificate["by_material"].items():
        y -= 6 * mm
        text(columns[0], y, MATERIALS.get(material, material), 10)
        text(columns[1], y, kg(row["grams"]), 10)
        text(columns[2], y, kg(row["co2e_g"]), 10)
        y -= 2.5 * mm
        page.line(left, y, right, y)

    # How it was counted.
    y -= 9 * mm
    issued = datetime.fromisoformat(certificate["created_at"]).astimezone(tz)
    y = paragraph(
        y,
        "Cuenta solo el material que llegó a un comprador en ese mes, depositado en los "
        "contenedores de Zyrcle y verificado por ellos: no es el total de residuos de la "
        "institución. Las emisiones evitadas usan los factores de reciclaje frente a relleno de "
        f"EPA WARM versión 16 ({certificate['factors_version']}). Es una cifra indicativa: no es "
        "un crédito de carbono. Ningún depósito entra en dos certificados. Emitido por "
        f"{certificate['issued_by']} el {issued.day} de {MONTHS[issued.month - 1]} de "
        f"{issued.year}.",
    )

    # How to verify it.
    y -= 6 * mm
    url = verify_url(web_url, certificate["id"])
    qr_size = 34 * mm
    widget = QrCodeWidget(url, barLevel="M")
    x0, y0, x1, y1 = widget.getBounds()
    drawing = Drawing(
        qr_size, qr_size, transform=[qr_size / (x1 - x0), 0, 0, qr_size / (y1 - y0), 0, 0]
    )
    drawing.add(widget)
    renderPDF.draw(drawing, page, right - qr_size, y - qr_size + 4 * mm)
    text(left, y, "Verifícalo", 11, "Helvetica-Bold")
    y -= 6 * mm
    proof = [
        "Escanea el código o abre la dirección de abajo: tu navegador recalcula la huella de cada",
        "depósito y la compara con la que quedó escrita en ZyrcleChain"
        + (" y con la copia en IPFS." if certificate.get("ipfs_cid") else "."),
    ]
    for line in proof:
        text(left, y, line, 8.5, color=MUTED)
        y -= 4.2 * mm
    y -= 1.5 * mm
    rows = [
        ("Página", url),
        ("Raíz de Merkle", certificate["merkle_root"]),
        ("Copia en IPFS", certificate.get("ipfs_cid") or "sin copia"),
        ("Transacción", certificate.get("anchor_tx") or "pendiente de anclar"),
        ("Cadena", f"ZyrcleChain (id {chain_id}), red de prueba de Avalanche"),
    ]
    for label, value in rows:
        text(left, y, label, 7.5, "Helvetica-Bold", MUTED)
        font, size = (
            ("Courier", 6.6)
            if value.startswith("0x") or label == "Copia en IPFS"
            else ("Helvetica", 7.5)
        )
        text(left + 26 * mm, y, value, size, font, FOREST)
        y -= 4.4 * mm

    page.setFont("Helvetica", 7)
    page.setFillColor(MUTED)
    made = now.astimezone(tz)
    page.drawString(
        left,
        14 * mm,
        f"Generado el {made.day} de {MONTHS[made.month - 1]} de {made.year}, {made:%H:%M} "
        f"(hora de {tz.key}). Zyrcle · {web_url.rstrip('/')}",
    )
    page.showPage()
    page.save()
    return out.getvalue()
