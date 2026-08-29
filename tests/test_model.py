"""
Tests obligatoires du cahier des charges (section 17) portant sur le
modele mathematique (model.py). Lancer avec : pytest
"""

import math
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest

from model import predict_delta, round_to_step, compute_new_length


def test_t1_basic_calculation_returns_numeric_value():
    delta = predict_delta(1000)
    assert isinstance(delta, float)
    assert math.isfinite(delta)


def test_t2_delta_and_new_length_are_consistent():
    delta_continuous, delta_rounded, new_length = compute_new_length(1500)
    assert new_length == 1500 + delta_rounded
    assert delta_rounded % 5 == 0


def test_t3_zero_length_raises_error():
    with pytest.raises(ValueError):
        predict_delta(0)


def test_t3_negative_length_raises_error():
    with pytest.raises(ValueError):
        predict_delta(-100)


def test_t4_none_length_raises_error():
    with pytest.raises(ValueError):
        predict_delta(None)


def test_t5_batch_processing_gives_one_output_per_wire():
    lengths = [500, 1000, 1500, 2000, 2500]
    results = [compute_new_length(length) for length in lengths]
    assert len(results) == len(lengths)


def test_t6_same_length_gives_same_delta_determinism():
    delta_1 = predict_delta(1234.5)
    delta_2 = predict_delta(1234.5)
    assert delta_1 == delta_2


def test_rounding_examples_from_cahier():
    assert round_to_step(-17.8) == -20
    assert round_to_step(-12.1) == -10
    assert round_to_step(-7.4) == -5
    assert round_to_step(3.2) == 5


def test_t7_reference_example_from_real_data():
    # Old_E.xlsx -> New_E.xlsx : L=2048 -> New=2028 (Delta reel = -20)
    delta_continuous, delta_rounded, new_length = compute_new_length(2048)
    assert delta_rounded == -20
    assert new_length == 2028