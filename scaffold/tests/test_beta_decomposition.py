"""Eight tests for orthogonal β-space algebra (core novelty)."""

import math

import pytest

from paper_c_eesd.fragility.beta_decomposition import (
    compose_independent_betas,
    decompose_inflation_orthogonal,
    iter_component_triples,
    pythagorean_check,
)


def test_compose_independent_betas_empty_is_zero() -> None:
    assert compose_independent_betas({}) == 0.0


def test_compose_345_triangle() -> None:
    assert math.isclose(compose_independent_betas({"a": 3, "b": 4}), 5.0)


def test_inflation_excess_5_3_gives_4() -> None:
    r = decompose_inflation_orthogonal(5.0, 3.0)
    assert math.isclose(r.beta_excess, 4.0)
    assert r.flags == ()


def test_inflation_equal_gives_zero() -> None:
    r = decompose_inflation_orthogonal(0.4, 0.4)
    assert r.beta_excess == 0.0


def test_neg_component_raises() -> None:
    with pytest.raises(ValueError, match="must be a finite non-negative"):
        compose_independent_betas({"x": -1.0})


def test_optimistic_lt_strict_flag() -> None:
    r = decompose_inflation_orthogonal(0.1, 0.5)
    assert r.beta_excess == 0.0
    assert "optimistic_lt_strict" in r.flags


def test_pythagorean_check_passes() -> None:
    assert pythagorean_check({"a": 3, "b": 4}, 5.0)


def test_iter_triples_sum_fraction_one() -> None:
    csum = 0.0
    for _name, _b, frac in iter_component_triples({"a": 3, "b": 4, "c": 0.0}):
        csum += frac
    assert math.isclose(csum, 1.0)
