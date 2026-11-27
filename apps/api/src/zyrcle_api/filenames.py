"""Names for the files the API hands out (exports, PDFs)."""

import re
import unicodedata


def slug(name: str, fallback: str, limit: int = 40) -> str:
    """'Cafetería Central' as 'cafeteria-central': ASCII, lowercase, hyphens, at most `limit`."""
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_name.lower()).strip("-")[:limit].strip("-") or fallback
