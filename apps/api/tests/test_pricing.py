from zyrcle_api.pricing import advance_cop


def test_half_of_the_reference_value():
    # 2.4 kg of PET at 1,000 COP/kg is worth 2,400 COP; the advance is half of it.
    assert advance_cop(2_400, 1_000, 5_000, 5_000) == 1_200


def test_rounds_down_to_whole_pesos():
    assert advance_cop(71, 1_000, 5_000, 5_000) == 35  # 35.5 COP


def test_capped_by_the_contract_limit():
    assert advance_cop(50_000, 4_000, 5_000, 5_000) == 5_000


def test_nothing_for_empty_deposits_or_missing_prices():
    assert advance_cop(0, 1_000, 5_000, 5_000) == 0
    assert advance_cop(500, 0, 5_000, 5_000) == 0
