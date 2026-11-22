from zyrcle_api.chain import Chain, deposit_id


def test_subnet_evm_block_headers_are_accepted():
    # Subnet-EVM headers carry more than 32 bytes of extraData; without this middleware web3.py
    # raises ExtraDataLengthError on the first block it reads (found deploying to ZyrcleChain).
    chain = Chain("http://127.0.0.1:1")
    assert "subnet_evm_extradata" in [name for _, name in chain.w3.middleware_onion.middleware]


def test_deposit_id_is_the_session_uuid_left_padded():
    import uuid

    sid = uuid.UUID("12345678-1234-5678-1234-567812345678")
    assert deposit_id(sid) == b"\0" * 16 + sid.bytes
