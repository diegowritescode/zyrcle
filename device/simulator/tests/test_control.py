from fastapi.testclient import TestClient
from zyrcle_protocol import generate_private_key

from zyrcle_sim import DeviceRunner, SimulatedContainer
from zyrcle_sim.control import create_control_app


def test_deposit_only_while_the_lid_is_open():
    runner = DeviceRunner(SimulatedContainer("ctr-0001", seed=1), generate_private_key())
    client = TestClient(create_control_app({"ctr-0001": runner}))
    assert (
        client.post("/containers/ctr-0001/deposit", json={"item": "pet_bottle"}).status_code == 409
    )
    runner.c.open_for("s1")
    r = client.post("/containers/ctr-0001/deposit", json={"item": "pet_bottle", "count": 2})
    assert r.status_code == 200 and r.json()["session_id"] == "s1"
    assert client.get("/containers").json()[0]["lid_open"] is True
    assert (
        client.post("/containers/ctr-0001/deposit", json={"item": "plutonium"}).status_code == 422
    )
    assert client.post("/containers/nope/deposit", json={"item": "stone"}).status_code == 404
