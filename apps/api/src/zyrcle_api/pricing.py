"""Advance sizing. Pure."""


def advance_cop(deposited_g: int, cop_per_kg: int, ratio_bps: int, max_cop: int) -> int:
    """ratio x price x kg, rounded down to whole pesos, capped at the per-deposit maximum."""
    if deposited_g <= 0 or cop_per_kg <= 0 or ratio_bps <= 0:
        return 0
    return min(deposited_g * cop_per_kg * ratio_bps // (10_000 * 1_000), max_cop)
