from mutohplot.hard_clip import get_hard_clip
from mutohplot.transform.hard_clip import hard_clip_center_correction


def test_norm_correction():
    correction = hard_clip_center_correction(get_hard_clip("norm"))
    assert correction.first_mm == -10.0
    assert correction.second_mm == 0.0


def test_exp_correction():
    correction = hard_clip_center_correction(get_hard_clip("exp"))
    assert correction.first_mm == -10.0
    assert correction.second_mm == 0.0


def test_type1_correction():
    correction = hard_clip_center_correction(get_hard_clip("type1"))
    assert correction.first_mm == -10.0
    assert correction.second_mm == 0.0


def test_type3_correction():
    correction = hard_clip_center_correction(get_hard_clip("type3"))
    assert correction.first_mm == -7.5
    assert correction.second_mm == 0.0


def test_none_correction():
    correction = hard_clip_center_correction(get_hard_clip("none"))
    assert correction.first_mm == 0.0
    assert correction.second_mm == 0.0
