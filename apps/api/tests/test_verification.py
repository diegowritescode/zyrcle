import pytest

from zyrcle_api.domain.verification import Measurement, Outcome, verify


def m(**kw):
    base = dict(
        declared_material="pet",
        tare_g=10_000,
        final_g=10_075,
        added_volume_ml=1_800,
        volume_uncertainty_ml=500,
        metal_detected=False,
        camera_label="pet",
    )
    return Measurement(**{**base, **kw})


def test_three_pet_bottles_are_accepted():
    v = verify(m())
    assert v.outcome is Outcome.OK and v.deposited_g == 75 and v.reasons == []


def test_stone_declared_as_pet_goes_to_review():
    v = verify(m(final_g=12_000, added_volume_ml=800, camera_label="rock"))
    assert v.outcome is Outcome.SUSPECT
    assert v.score == 0.0
    assert any("too dense" in r for r in v.reasons)


def test_sensor_noise_alone_does_not_flag_an_honest_deposit():
    # Glass bottle: 350 g, but the distance sensor under-reads the volume by its full uncertainty.
    v = verify(
        m(declared_material="glass", final_g=10_350, added_volume_ml=0, camera_label="glass")
    )
    assert v.outcome is Outcome.OK


def test_metal_in_plastic_lowers_the_score():
    v = verify(m(metal_detected=True))
    assert v.outcome is Outcome.SUSPECT and v.score == 0.3


def test_declared_metal_without_metal_signal():
    v = verify(m(declared_material="metal", camera_label="metal", added_volume_ml=1_000))
    assert v.outcome is Outcome.SUSPECT


def test_camera_disagreement_alone_goes_to_review():
    assert verify(m(camera_label="glass")).outcome is Outcome.SUSPECT


def test_unknown_camera_label_is_neutral():
    assert verify(m(camera_label=None)).outcome is Outcome.OK


def test_nothing_deposited():
    v = verify(m(final_g=10_005))
    assert v.outcome is Outcome.EMPTY and v.deposited_g == 0


def test_material_taken_out_is_suspect():
    assert verify(m(final_g=9_000)).outcome is Outcome.SUSPECT


def test_unknown_material_is_a_programming_error():
    with pytest.raises(ValueError):
        verify(m(declared_material="uranium"))
