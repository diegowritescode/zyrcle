"""Material verification (docs/architecture.md, section 6).

Combines the cheap signals a container has into one confidence score. Pure: no I/O.

Density is the main defence against stones, sand or water: added weight divided by added volume.
The volume comes from a distance sensor over the container's cross-section, so it carries an
uncertainty. To avoid flagging honest deposits because of sensor noise, the check uses the most
favourable volume (measured + uncertainty): only a deposit that is too dense even then is flagged.
"""

from dataclasses import dataclass, field
from enum import StrEnum


class Outcome(StrEnum):
    OK = "ok"
    SUSPECT = "suspect"
    EMPTY = "empty"


# Upper bound of loose bulk density per material, g/ml. Initial estimates, to be calibrated with
# data from real containers. Stones, sand and water are all above 1.4 g/ml.
MAX_BULK_DENSITY_G_PER_ML: dict[str, float] = {
    "pet": 0.15,
    "hdpe": 0.20,
    "paper": 0.35,
    "cardboard": 0.30,
    "glass": 0.90,
    "metal": 0.25,
}
METALLIC = frozenset({"metal"})


@dataclass(frozen=True)
class Rules:
    min_deposit_g: int = 20  # below this, nothing was deposited (scale noise)
    removal_tolerance_g: int = 30  # a drop larger than this means material was taken out
    threshold: float = 0.7


@dataclass(frozen=True)
class Measurement:
    declared_material: str
    tare_g: int
    final_g: int
    added_volume_ml: int
    volume_uncertainty_ml: int
    metal_detected: bool
    camera_label: str | None = None


@dataclass(frozen=True)
class Verdict:
    outcome: Outcome
    score: float
    deposited_g: int
    reasons: list[str] = field(default_factory=list)


def verify(m: Measurement, rules: Rules = Rules()) -> Verdict:
    if m.declared_material not in MAX_BULK_DENSITY_G_PER_ML:
        raise ValueError(f"unknown material {m.declared_material!r}")
    delta = m.final_g - m.tare_g
    if delta < -rules.removal_tolerance_g:
        return Verdict(
            Outcome.SUSPECT, 0.0, 0, [f"weight dropped by {-delta} g during the session"]
        )
    if delta < rules.min_deposit_g:
        return Verdict(Outcome.EMPTY, 1.0, 0, ["no material deposited"])

    score = 1.0
    reasons: list[str] = []

    best_case_volume = max(m.added_volume_ml + m.volume_uncertainty_ml, 1)
    min_density = delta / best_case_volume
    max_density = MAX_BULK_DENSITY_G_PER_ML[m.declared_material]
    if min_density > max_density:
        score = 0.0
        reasons.append(
            f"too dense for {m.declared_material}: at least {min_density:.2f} g/ml "
            f"(max {max_density:.2f})"
        )

    if m.metal_detected and m.declared_material not in METALLIC:
        score *= 0.3
        reasons.append(f"metal detected in a {m.declared_material} deposit")
    elif not m.metal_detected and m.declared_material in METALLIC:
        score *= 0.3
        reasons.append("declared metal but the metal sensor saw none")

    if m.camera_label is not None and m.camera_label != m.declared_material:
        score *= 0.5
        reasons.append(f"camera saw {m.camera_label!r}, declared {m.declared_material!r}")

    outcome = Outcome.OK if score >= rules.threshold else Outcome.SUSPECT
    return Verdict(outcome, round(score, 3), delta, reasons)
