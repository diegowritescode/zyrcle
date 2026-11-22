import pytest

from zyrcle_sim import SimulatedContainer
from zyrcle_sim.container import LidClosed


def test_deposit_changes_weight_and_distance():
    c = SimulatedContainer("ctr-0001", seed=1)
    opened = c.open_for("s1")
    c.deposit("pet_bottle", 3)
    m = c.close()
    assert m["session_id"] == "s1" and m["tare_g"] == opened["weight_g"]
    assert 65 <= m["final_g"] - m["tare_g"] <= 85
    assert m["fill_before_mm"] - m["fill_after_mm"] in range(5, 10)  # 1,800 ml over 0.25 m²
    assert m["camera_label"] == "pet" and m["metal"] is False


def test_cannot_deposit_with_lid_closed():
    with pytest.raises(LidClosed):
        SimulatedContainer("ctr-0001").deposit("pet_bottle")


def test_metal_sensor_and_camera_follow_the_items():
    c = SimulatedContainer("ctr-0001", seed=2)
    c.open_for("s1")
    c.deposit("aluminum_can", 2)
    c.deposit("pet_bottle")
    m = c.close()
    assert m["metal"] is True and m["camera_label"] == "metal"
