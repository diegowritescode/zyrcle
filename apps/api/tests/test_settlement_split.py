"""How a sale is split (docs/adr/0013): pure, so checked with generated inputs."""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from zyrcle_api.domain.settlement import Parts, parts, pro_rata


def test_parts_follow_the_shares_rounded_down():
    assert parts(30_000, 6_500, 1_500, 1_000) == Parts(19_500, 4_500, 3_000)
    assert parts(999, 6_500, 1_500, 1_000) == Parts(649, 149, 99)


@given(
    total=st.integers(min_value=0, max_value=10**12),
    weights=st.lists(st.integers(min_value=0, max_value=10**7), min_size=1, max_size=60),
)
def test_pro_rata_never_pays_more_than_the_total(total, weights):
    split = pro_rata(total, weights)
    assert len(split) == len(weights)
    assert sum(split) <= total
    assert all(s >= 0 for s in split)
    assert all(s == 0 for s, w in zip(split, weights, strict=True) if w == 0)
    # Rounding down loses less than one peso per party.
    if sum(weights):
        assert total - sum(split) < len(weights)


@given(st.integers(min_value=1, max_value=10**6), st.integers(min_value=1, max_value=10**6))
def test_more_grams_never_get_less(a, b):
    small, big = sorted((a, b))
    x, y = pro_rata(1_000_000, [small, big])
    assert x <= y


def test_bad_input_is_refused():
    with pytest.raises(ValueError):
        pro_rata(-1, [1])
    with pytest.raises(ValueError):
        pro_rata(10, [1, -1])
    assert pro_rata(10, [0, 0]) == [0, 0]
