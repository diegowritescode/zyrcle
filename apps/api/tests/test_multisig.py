"""The Safe that takes ZyrcleChain's admin powers (docs/adr/0040), on anvil: proposals signed by
owners, the 2-of-3 threshold, and the whole handover of the eight powers."""

import json
import pathlib

import pytest
from eth_account import Account
from eth_utils import to_checksum_address

from zyrcle_api.chain import Chain, load_account
from zyrcle_api.multisig import NATIVE_MINTER, PRECOMPILES, Proposal, sign_with_key
from zyrcle_api.safe_ops import PROXY_ADMIN_SLOT, SET_ADMIN_ABI, VALIDATOR_MANAGER, SafeOps

from .conftest import ANVIL_KEYS

pytestmark = pytest.mark.integration
FIXTURES = pathlib.Path(__file__).parent / "fixtures"


@pytest.fixture
def owners():
    return [Account.create() for _ in range(3)]


async def test_a_proposal_needs_two_owner_signatures_and_runs_once(chain_env, owners):
    chain, admin = chain_env["chain"], load_account(ANVIL_KEYS["admin"])
    ops = SafeOps(chain, None, None)
    stack = await ops.deploy(admin, [o.address for o in owners], threshold=2)
    safe = stack["safe"]
    assert await ops.threshold(safe) == 2
    assert {a.lower() for a in await ops.owners(safe)} == {o.address.lower() for o in owners}

    target = Account.create().address
    minter = chain.w3.eth.contract(address=to_checksum_address(NATIVE_MINTER), abi=SET_ADMIN_ABI)
    data = minter.encode_abi("setEnabled", args=[to_checksum_address(target)])
    p = await ops.propose(safe, NATIVE_MINTER, data, "habilitar una dirección")
    assert p.tx_hash() == await ops.onchain_hash(p)  # the same hash the Safe computes

    p.add_signature(sign_with_key(p, owners[0].key.hex()), await ops.owners(safe))
    with pytest.raises(ValueError, match="needs more"):
        await ops.execute(admin, p)
    stranger = sign_with_key(p, Account.create().key.hex())
    with pytest.raises(ValueError, match="not an owner"):
        p.add_signature(stranger, await ops.owners(safe))

    # It travels as a file between signers; a changed byte is caught.
    travelled = Proposal.from_json(p.to_json())
    travelled.add_signature(sign_with_key(travelled, owners[2].key.hex()), await ops.owners(safe))
    tampered = json.loads(travelled.to_json())
    tampered["data"] = tampered["data"][:-2] + "00"
    with pytest.raises(ValueError, match="changed"):
        Proposal.from_json(json.dumps(tampered))

    await ops.execute(admin, travelled)
    assert await minter.functions.readAllowList(to_checksum_address(target)).call() == 1
    assert await ops.nonce(safe) == 1
    with pytest.raises(ValueError, match="moved on"):
        await ops.execute(admin, travelled)


async def install(chain, address: str, code: str) -> None:
    await chain.w3.provider.make_request("anvil_setCode", [address, code])


async def test_the_handover_moves_all_eight_powers_and_leaves_the_admin_key_none(chain_env, owners):
    chain, admin = chain_env["chain"], load_account(ANVIL_KEYS["admin"])
    w3 = chain.w3
    # anvil has no precompiles: the allow-list stand-in at the other three, Ownable stand-ins for
    # the validator manager and its proxy admin.
    minter_code = json.loads((FIXTURES / "AnvilNativeMinter.json").read_text())["deployedBytecode"]
    for address in PRECOMPILES.values():
        if address != NATIVE_MINTER:
            await install(chain, address, minter_code)
        c = w3.eth.contract(address=to_checksum_address(address), abi=SET_ADMIN_ABI)
        await chain._send(admin, c.functions.setAdmin(admin.address))
    ownable = json.loads((FIXTURES / "OwnableMock.json").read_text())
    mock = w3.eth.contract(abi=ownable["abi"], bytecode=ownable["bytecode"])
    proxy_admin = (await chain._send(admin, mock.constructor(admin.address)))["contractAddress"]
    await install(chain, VALIDATOR_MANAGER, ownable["deployedBytecode"])
    owner_word = "0x" + "00" * 12 + admin.address[2:].lower()
    await w3.provider.make_request("anvil_setStorageAt", [VALIDATOR_MANAGER, "0x0", owner_word])
    admin_word = "0x" + "00" * 12 + proxy_admin[2:].lower()
    await w3.provider.make_request(
        "anvil_setStorageAt", [VALIDATOR_MANAGER, PROXY_ADMIN_SLOT, admin_word]
    )
    # A Treasury and a factory of its own, deployed through a separate client: deploying through the
    # shared one would point the rest of the suite at them.
    fresh = Chain(chain_env["rpc"])
    treasury = await fresh.deploy_treasury(admin, admin.address, admin.address)
    factory = await fresh.deploy_account_factory(admin, admin.address)

    ops = SafeOps(chain, factory, treasury)
    stack = await ops.deploy(admin, [o.address for o in owners], threshold=2)
    safe = stack["safe"]
    before = await ops.status(admin.address, safe)
    assert len(before) == 8 and all(r["admin_key"] and not r["safe"] for r in before)

    with pytest.raises(ValueError, match="does not hold"):
        await ops.renounce_roles(admin, safe)  # never before the Safe holds the roles

    assert len(await ops.grant_to_safe(admin, safe)) == 6  # 4 precompiles, 2 contract roles

    async def signed(p: Proposal) -> Proposal:
        for o in (owners[0], owners[1]):
            p.add_signature(sign_with_key(p, o.key.hex()), await ops.owners(safe))
        return p

    await ops.execute(admin, await signed(await ops.proof_proposal(safe)))
    assert set(await ops.transfer_ownerships(admin, safe)) == {
        "ValidatorManager",
        "ValidatorManager proxy admin",
    }
    revoke = await ops.revoke_proposal(safe, admin.address, stack["multisend"])
    await ops.execute(admin, await signed(revoke))
    assert set(await ops.renounce_roles(admin, safe)) == {"Treasury", "AccountFactory"}

    after = await ops.status(admin.address, safe)
    assert all(r["safe"] and not r["admin_key"] for r in after), after
    await fresh.w3.provider.disconnect()


def cli(chain_env, *args: str, stdin: str | None = None):
    import os
    import subprocess
    import sys

    env = {
        **os.environ,
        "ZYRCLE_CHAIN_RPC_URL": chain_env["rpc"],
        "ZYRCLE_TREASURY_ADDRESS": chain_env["treasury"],
        "ZYRCLE_ACCOUNT_FACTORY_ADDRESS": chain_env["factory"],
    }
    r = subprocess.run(
        [sys.executable, "-m", "zyrcle_api.cli", "safe", *args],
        env=env,
        input=stdin,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert r.returncode == 0, r.stderr
    return r.stdout


async def test_the_command_line_runs_the_first_steps_and_a_paper_key_signs(
    chain_env, owners, tmp_path
):
    admin_file = tmp_path / "admin.pk"
    admin_file.write_text(ANVIL_KEYS["admin"])
    owner_file = tmp_path / "owner.pk"
    owner_file.write_text(owners[0].key.hex())
    out = cli(
        chain_env,
        "deploy",
        "--admin-key-file",
        str(admin_file),
        "--owners",
        ",".join(o.address for o in owners),
        "--threshold",
        "2",
    )
    values = dict(line.split("=", 1) for line in out.split())
    safe = values["SAFE"]
    assert "SAFE_MULTISEND" in values
    cli(chain_env, "grant", "--admin-key-file", str(admin_file), "--safe", safe)
    proposal = tmp_path / "proof.json"
    cli(chain_env, "propose", "--safe", safe, "--what", "proof", "--out", str(proposal))
    first = cli(chain_env, "sign", "--proposal", str(proposal), "--key-file", str(owner_file))
    assert "1 of 2" in first
    # The paper key is typed, never written to a file.
    paper = cli(
        chain_env, "sign", "--proposal", str(proposal), "--key-file", "-", stdin=owners[2].key.hex()
    )
    assert "2 of 2" in paper
    assert "executed" in cli(
        chain_env, "exec", "--proposal", str(proposal), "--key-file", str(admin_file)
    )
    admin = load_account(ANVIL_KEYS["admin"]).address
    status = cli(chain_env, "status", "--safe", safe, "--admin", admin)
    assert "AccountFactory" in status and "Safe: sí" in status
