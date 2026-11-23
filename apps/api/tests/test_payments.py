"""Paying a campus merchant and redeeming ZYR for pesos (docs/adr/0029), on anvil."""

import pytest
from eth_account import Account

from zyrcle_api.chain import WEI_PER_COP

from .helpers import OPS, headers, sign_in, wait_for

pytestmark = pytest.mark.integration


def sign(person: dict, typed: dict) -> dict:
    """What the phone does: sign the EIP-712 Execute the API returned."""
    message = typed["message"]
    full = {
        **typed,
        "message": {
            "calls": [
                {
                    "target": c["target"],
                    "value": int(c["value"]),
                    "data": bytes.fromhex(c["data"].removeprefix("0x")),
                }
                for c in message["calls"]
            ],
            "nonce": int(message["nonce"]),
            "deadline": int(message["deadline"]),
        },
    }
    signed = Account.sign_typed_data(person["key"].key, full_message=full)
    return {
        "signature": "0x" + signed.signature.hex().removeprefix("0x"),
        "deadline": int(message["deadline"]),
        "nonce": int(message["nonce"]),
    }


async def fund(chain, address: str, pesos: int) -> None:
    await chain.w3.provider.make_request("anvil_setBalance", [address, hex(pesos * WEI_PER_COP)])


async def zyr(chain, address: str) -> int:
    return await chain.balance_wei(address) // WEI_PER_COP


async def merchant_account(client, settings, name="Cafetería Central") -> dict:
    shop = await sign_in(client, settings)
    r = await client.post(
        "/v1/operator/merchants",
        headers=OPS,
        json={"address": shop["address"], "name": name, "nit": "900123456-7"},
    )
    assert r.status_code == 201, r.text
    return shop


async def wait_status(client, person, payment_id: str, status: str) -> dict:
    holder: dict = {}

    async def ok() -> bool:
        holder["p"] = (
            await client.get(f"/v1/payments/{payment_id}", headers=headers(person))
        ).json()
        return holder["p"]["status"] in (status, "failed")

    await wait_for(ok, timeout=20)
    return holder["p"]


async def test_a_participant_pays_a_merchant_without_gas_or_a_deployed_account(
    client, settings, chain_env
):
    chain = chain_env["chain"]
    shop = await merchant_account(client, settings)
    payer = await sign_in(client, settings)
    await fund(chain, payer["address"], 100)
    assert not await chain.is_deployed(payer["address"])
    me = (await client.get("/v1/me", headers=headers(shop))).json()
    assert me["merchant"] == "Cafetería Central"

    charge = (
        await client.post(
            "/v1/merchant/charges",
            headers=headers(shop),
            json={"amount_cop": 30, "concept": "Café"},
        )
    ).json()
    assert charge["qr"] == f"zyrcle://p/{charge['id']}" and charge["status"] == "open"
    shown = (await client.get(f"/v1/payments/{charge['id']}", headers=headers(payer))).json()
    assert shown["merchant"] == "Cafetería Central" and shown["amount_cop"] == 30

    typed = (
        await client.post(f"/v1/payments/{charge['id']}/intent", headers=headers(payer))
    ).json()
    assert typed["domain"]["verifyingContract"].lower() == payer["address"]
    assert typed["message"]["calls"][0]["target"].lower() == shop["address"]

    # A signature from another key is refused before anything reaches the chain.
    stranger = await sign_in(client, settings)
    r = await client.post(
        f"/v1/payments/{charge['id']}/pay", headers=headers(payer), json=sign(stranger, typed)
    )
    assert r.status_code == 403

    r = await client.post(
        f"/v1/payments/{charge['id']}/pay", headers=headers(payer), json=sign(payer, typed)
    )
    assert r.status_code == 200 and r.json()["status"] == "paying"
    paid = await wait_status(client, payer, charge["id"], "paid")
    assert paid["status"] == "paid" and paid["tx_hash"]
    assert await zyr(chain, shop["address"]) == 30
    assert await zyr(chain, payer["address"]) == 70
    assert await chain.is_deployed(payer["address"])  # deployed by the relayer on the way

    # A second payment uses the next nonce; a paid charge cannot be paid again.
    again = (
        await client.post("/v1/merchant/charges", headers=headers(shop), json={"amount_cop": 20})
    ).json()
    typed2 = (
        await client.post(f"/v1/payments/{again['id']}/intent", headers=headers(payer))
    ).json()
    assert typed2["message"]["nonce"] == "1"
    await client.post(
        f"/v1/payments/{again['id']}/pay", headers=headers(payer), json=sign(payer, typed2)
    )
    assert (await wait_status(client, payer, again["id"], "paid"))["status"] == "paid"
    r = await client.post(f"/v1/payments/{charge['id']}/intent", headers=headers(payer))
    assert r.status_code == 409

    # Not enough ZYR is said before signing.
    big = (
        await client.post(
            "/v1/merchant/charges", headers=headers(shop), json={"amount_cop": 10_000}
        )
    ).json()
    r = await client.post(f"/v1/payments/{big['id']}/intent", headers=headers(payer))
    assert r.status_code == 409
    # Only merchants charge.
    r = await client.post("/v1/merchant/charges", headers=headers(payer), json={"amount_cop": 5})
    assert r.status_code == 403


async def test_a_merchant_redeems_zyr_and_the_operator_pays_or_refunds(client, settings, chain_env):
    chain = chain_env["chain"]
    shop = await merchant_account(client, settings, "Papelería del Campus")
    await fund(chain, shop["address"], 500)
    before = await chain.state()

    intent = (
        await client.post(
            "/v1/merchant/redemptions", headers=headers(shop), json={"amount_cop": 200}
        )
    ).json()
    r = await client.post(
        f"/v1/merchant/redemptions/{intent['id']}/sign",
        headers=headers(shop),
        json=sign(shop, intent["typed_data"]),
    )
    assert r.status_code == 200 and r.json()["status"] == "requested"

    async def pending() -> bool:
        rows = (await client.get("/v1/operator/redemptions?status=pending", headers=OPS)).json()
        return any(x["id"] == intent["id"] for x in rows)

    await wait_for(pending, timeout=20)
    assert await zyr(chain, shop["address"]) == 300  # held by the Treasury

    r = await client.post(
        f"/v1/operator/redemptions/{intent['id']}/settle",
        headers=OPS,
        json={"bank_ref": "BANCO-REDEEM-1"},
    )
    assert r.status_code == 200 and r.json()["status"] == "settled"
    after = await chain.state()
    assert before.backing_cop - after.backing_cop == 200  # the pesos left the bank
    r = await client.post(
        f"/v1/operator/redemptions/{intent['id']}/settle", headers=OPS, json={"bank_ref": "x"}
    )
    assert r.status_code == 409

    second = (
        await client.post(
            "/v1/merchant/redemptions", headers=headers(shop), json={"amount_cop": 100}
        )
    ).json()
    await client.post(
        f"/v1/merchant/redemptions/{second['id']}/sign",
        headers=headers(shop),
        json=sign(shop, second["typed_data"]),
    )

    async def second_pending() -> bool:
        rows = (await client.get("/v1/operator/redemptions?status=pending", headers=OPS)).json()
        return any(x["id"] == second["id"] for x in rows)

    await wait_for(second_pending, timeout=20)
    assert await zyr(chain, shop["address"]) == 200
    r = await client.post(f"/v1/operator/redemptions/{second['id']}/refund", headers=OPS)
    assert r.status_code == 200 and r.json()["status"] == "refunded"
    assert await zyr(chain, shop["address"]) == 300  # back to the merchant
    home = (await client.get("/v1/merchant", headers=headers(shop))).json()
    assert {x["status"] for x in home["redemptions"]} == {"settled", "refunded"}
