"""Chain chores from the command line (docs/infrastructure.md, runbooks 9.6 and 9.12): gas for the
backend's keys, and retiring an old Treasury from the NativeMinter allow list."""

import os
import subprocess
import sys

from eth_account import Account

from zyrcle_api.chain import load_account, load_account_file

from .conftest import ANVIL_KEYS


def cli(chain_env: dict, *args: str) -> subprocess.CompletedProcess:
    env = {
        **os.environ,
        "ZYRCLE_CHAIN_RPC_URL": chain_env["rpc"],
        "ZYRCLE_TREASURY_ADDRESS": chain_env["treasury"],
    }
    return subprocess.run(
        [sys.executable, "-m", "zyrcle_api.cli", "chain", *args],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )


async def test_fund_sends_gas_and_balance_reads_it(chain_env, tmp_path):
    admin_file = tmp_path / "admin.key"
    admin_file.write_text(ANVIL_KEYS["admin"])
    to = Account.create().address
    fund = ("fund", "--from-key-file", str(admin_file), "--to", to, "--amount-zyr")
    r = cli(chain_env, *fund, "1.5")
    assert r.returncode == 0, r.stderr
    assert await chain_env["chain"].balance_wei(to) == 15 * 10**17
    assert f"{to} 1.5 ZYR" in cli(chain_env, "balance", "--address", to).stdout
    bad = cli(chain_env, *fund, "0")
    assert bad.returncode != 0 and "positive" in bad.stderr


async def test_minter_revoke_retires_an_old_treasury_but_never_the_current_one(chain_env, tmp_path):
    chain = chain_env["chain"]
    admin_file = tmp_path / "admin.key"
    admin_file.write_text(ANVIL_KEYS["admin"])
    old = Account.create().address
    await chain._send(load_account(ANVIL_KEYS["admin"]), chain.minter.functions.setEnabled(old))
    assert await chain.minting_role(old) == 1

    r = cli(chain_env, "minter-revoke", "--admin-key-file", str(admin_file), "--address", old)
    assert r.returncode == 0, r.stderr
    assert await chain.minting_role(old) == 0
    again = cli(chain_env, "minter-revoke", "--admin-key-file", str(admin_file), "--address", old)
    assert "nothing to do" in again.stdout

    current = chain_env["treasury"]
    r = cli(chain_env, "minter-revoke", "--admin-key-file", str(admin_file), "--address", current)
    assert r.returncode != 0 and "in use" in r.stderr
    assert await chain.minting_role(current) == 1


def test_a_new_key_file_is_private_and_only_its_address_is_printed(tmp_path):
    out = tmp_path / "guardian.pk"
    r = subprocess.run(
        [sys.executable, "-m", "zyrcle_api.cli", "keys", "new", "--out", str(out)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert r.returncode == 0, r.stderr
    address = r.stdout.strip()
    assert oct(out.stat().st_mode & 0o777) == "0o600"
    assert load_account_file(str(out)).address == address
    assert out.read_text().strip() not in r.stdout
    again = subprocess.run(
        [sys.executable, "-m", "zyrcle_api.cli", "keys", "new", "--out", str(out)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert again.returncode != 0 and "not overwritten" in again.stderr
