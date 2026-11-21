import unittest

from pchain_address import p_chain_address

# The ewoq key is the public, well-known key of Avalanche local networks.
EWOQ = "56289e99c94b6912bfc12adc093c9b51124f0dc54ac7a766b2bc5ccf558d8027"


class PChainAddressTest(unittest.TestCase):
    def test_matches_avalanchego_for_ewoq(self):
        self.assertEqual(p_chain_address(EWOQ, "custom"), "P-custom18jma8ppw3nhx5r4ap8clazz0dps7rv5u9xde7p")

    def test_rejects_zero_key(self):
        with self.assertRaises(ValueError):
            p_chain_address("00" * 32)


if __name__ == "__main__":
    unittest.main()
