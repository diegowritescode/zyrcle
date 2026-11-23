"""How a sale of one bag is split (docs/adr/0013). Pure: no I/O.

Amounts are whole pesos rounded down, so the parties never receive more than the Treasury's parts
(which it computes in wei); the dust stays unminted.
"""

from dataclasses import dataclass

BPS = 10_000


@dataclass(frozen=True)
class Parts:
    residents: int
    collector: int
    host: int


def parts(amount_cop: int, residents_bps: int, collector_bps: int, host_bps: int) -> Parts:
    """The pesos each side of a sale may receive, as the Treasury splits them."""
    return Parts(
        residents=amount_cop * residents_bps // BPS,
        collector=amount_cop * collector_bps // BPS,
        host=amount_cop * host_bps // BPS,
    )


def pro_rata(total: int, weights: list[int]) -> list[int]:
    """`total` split in proportion to `weights`, each rounded down. Never adds up to more than
    `total`; zero weights get zero. A total of zero weight gets nothing."""
    if total < 0 or any(w < 0 for w in weights):
        raise ValueError("amounts and weights must not be negative")
    whole = sum(weights)
    if whole == 0:
        return [0] * len(weights)
    return [total * w // whole for w in weights]
