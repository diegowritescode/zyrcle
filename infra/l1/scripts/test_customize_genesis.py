"""Tests for customize_genesis.py. Run: python3 -m unittest discover -s infra/l1/scripts"""

import copy
import json
import pathlib
import unittest

from customize_genesis import WEI_PER_ZYR, check, customize

FIXTURE = pathlib.Path(__file__).resolve().parent.parent / "genesis.local.json"
ADMIN = "0x8db97c7cece249c2b98bdc0226cc4c2a57bf52fc"


class CustomizeGenesisTest(unittest.TestCase):
    def setUp(self):
        self.base = json.loads(FIXTURE.read_text())
        # Recreate what the CLI emits: a random 1,000,000-coin prefund and an ICM deployer.
        self.base["alloc"]["5f069f86e2f9aac3ecb15dde696abc483f8e34e4"] = {"balance": hex(10**24)}
        self.base["alloc"]["38ac723e17a595548cb705ac94fde1cb293ef246"] = {"balance": hex(600 * WEI_PER_ZYR)}

    def test_only_admin_float_is_funded(self):
        out = customize(copy.deepcopy(self.base), ADMIN, 100)
        check(out, ADMIN, 100)
        funded = {a for a, v in out["alloc"].items() if int(v.get("balance", "0x0"), 16)}
        self.assertEqual(funded, {ADMIN[2:]})

    def test_predeployed_contracts_are_kept(self):
        out = customize(copy.deepcopy(self.base), ADMIN, 100)
        for addr in ("0c0deba5e0000000000000000000000000000000", "0feedc0de0000000000000000000000000000000"):
            self.assertIn(addr, out["alloc"])

    def test_is_idempotent(self):
        once = customize(copy.deepcopy(self.base), ADMIN, 100)
        twice = customize(copy.deepcopy(once), ADMIN, 100)
        self.assertEqual(once, twice)

    def test_rejects_bad_address(self):
        with self.assertRaises(ValueError):
            customize(copy.deepcopy(self.base), "0x1234", 100)

    def test_requires_warp(self):
        g = copy.deepcopy(self.base)
        del g["config"]["warpConfig"]
        with self.assertRaises(ValueError):
            customize(g, ADMIN, 100)


if __name__ == "__main__":
    unittest.main()
