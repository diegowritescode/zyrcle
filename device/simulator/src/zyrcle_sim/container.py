"""Physics of a simulated container. No networking here; see runner.py for the MQTT side.

Sensors and their noise:
- load cell (HX711): ±2 g per reading
- time-of-flight distance sensor (VL53L1X) looking down at the contents: ±1 mm
- inductive proximity sensor: true while metal is inside the deposit chamber
- camera + vision model: one label per deposit, or None when it cannot tell
"""

import random
from collections import Counter
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Item:
    name: str
    weight_g: int
    volume_ml: int  # loose volume it takes inside the container
    metal: bool
    label: str  # what the camera model reports


CATALOG: dict[str, Item] = {
    item.name: item
    for item in (
        Item("pet_bottle", 25, 600, False, "pet"),
        Item("hdpe_jug", 60, 1_500, False, "hdpe"),
        Item("aluminum_can", 15, 350, True, "metal"),
        Item("glass_bottle", 350, 500, False, "glass"),
        Item("cardboard_box", 200, 2_500, False, "cardboard"),
        Item("paper_stack", 300, 900, False, "paper"),
        # Cheating attempts
        Item("stone", 2_000, 800, False, "rock"),
        Item("full_water_bottle", 520, 600, False, "pet"),
    )
}


@dataclass
class Session:
    session_id: str
    tare_g: int
    fill_before_mm: int
    items: list[Item] = field(default_factory=list)


class LidClosed(Exception):
    pass


class SimulatedContainer:
    def __init__(
        self,
        device_id: str,
        area_mm2: int = 250_000,
        depth_mm: int = 900,
        contents_g: int = 4_000,
        contents_height_mm: int = 120,
        seed: int | None = None,
    ):
        self.device_id = device_id
        self.area_mm2 = area_mm2
        self.depth_mm = depth_mm
        self._weight_g = float(contents_g)
        self._distance_mm = float(depth_mm - contents_height_mm)
        self._rng = random.Random(seed)
        self.code: str | None = None
        self.session: Session | None = None

    # sensors -----------------------------------------------------------------
    def read_weight(self) -> int:
        return round(self._weight_g + self._rng.gauss(0, 2))

    def read_distance(self) -> int:
        return round(self._distance_mm + self._rng.gauss(0, 1))

    def metal_present(self) -> bool:
        return bool(self.session and any(i.metal for i in self.session.items))

    def camera_label(self) -> str | None:
        if not self.session or not self.session.items:
            return None
        label, _ = Counter(i.label for i in self.session.items).most_common(1)[0]
        return label

    # actuators ---------------------------------------------------------------
    @property
    def lid_open(self) -> bool:
        return self.session is not None

    def open_for(self, session_id: str) -> dict:
        self.session = Session(session_id, self.read_weight(), self.read_distance())
        return {
            "session_id": session_id,
            "weight_g": self.session.tare_g,
            "fill_mm": self.session.fill_before_mm,
        }

    def close(self) -> dict:
        """Close the lid and return the final measurement for the session that was open."""
        assert self.session is not None
        s = self.session
        measurement = {
            "session_id": s.session_id,
            "tare_g": s.tare_g,
            "final_g": self.read_weight(),
            "fill_before_mm": s.fill_before_mm,
            "fill_after_mm": self.read_distance(),
            "metal": self.metal_present(),
            "camera_label": self.camera_label(),
        }
        self.session = None
        return measurement

    # the outside world -------------------------------------------------------
    def deposit(self, item: Item | str, count: int = 1) -> None:
        if self.session is None:
            raise LidClosed(f"{self.device_id}: the lid is closed")
        item = CATALOG[item] if isinstance(item, str) else item
        for _ in range(count):
            self.session.items.append(item)
            self._weight_g += item.weight_g
            self._distance_mm -= item.volume_ml * 1000 / self.area_mm2
