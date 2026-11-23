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


def test_a_collector_takes_out_one_kind_at_a_time():
    c = SimulatedContainer("ctr-0001", contents_g=0, seed=3)
    c.open_for("s1")
    c.deposit("pet_bottle", 4)
    c.deposit("hdpe_jug", 2)
    c.deposit("stone")
    c.close()
    assert c.contents() == {"pet": 100, "hdpe": 120, "rock": 2_000}

    c.open_for("collection")
    before = c.read_weight()
    assert c.take_out("pet") == 100
    assert abs(before - 100 - c.read_weight()) <= 10  # within the scale's noise
    assert c.take_out("glass") == 0  # nothing of that kind inside
    assert c.take_out() == 2_120  # everything left: the HDPE and the stone
    assert c.contents() == {}
    m = c.close()
    assert abs(m["final_g"]) <= 10 and m["fill_after_mm"] in range(895, 905)


def test_cannot_take_out_with_lid_closed():
    with pytest.raises(LidClosed):
        SimulatedContainer("ctr-0001").take_out("pet")


def test_contents_survive_a_restart(tmp_path):
    state = tmp_path / "ctr-0001.state.json"
    c = SimulatedContainer("ctr-0001", state_path=state)
    c.open_for("s1")
    c.deposit("glass_bottle", 3)
    c.close()
    again = SimulatedContainer("ctr-0001", state_path=state)
    assert again.contents() == {"glass": 1_050, "unknown": 4_000}
    assert abs(again.read_weight() - 5_050) <= 10
