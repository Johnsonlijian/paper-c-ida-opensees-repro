from pathlib import Path

import numpy as np

from paper_c_eesd.fragility import fit_lognormal_fragility_mle
from paper_c_eesd.fragility.fit_fragility import FragilityData, fit_lognormal_capacity_censored_mle
from paper_c_eesd.ida import ida_intensity_point_count
from paper_c_eesd.utils import load_config


def test_config_default_row_count_30_22_20() -> None:
    cd = Path(__file__).resolve().parent.parent / "configs"
    c = load_config("default", configs_dir=cd)
    assert c.ida.n_specimens == 30
    assert c.ida.n_ground_motions == 22
    assert c.ida.n_im_levels == 20
    assert c.output.get("ida_csv") == "data/ida_results/ida_raw_all.csv"
    n = ida_intensity_point_count("default", configs_dir=cd)
    assert n == 30 * 22 * 20


def test_config_pilot_overrides() -> None:
    cd = Path(__file__).resolve().parent.parent / "configs"
    c = load_config("pilot", configs_dir=cd)
    assert c.ida.n_specimens == 5
    n = ida_intensity_point_count("pilot", configs_dir=cd)
    assert n == 5 * 5 * 5


def test_mle_synthetic_lognormal_fragility() -> None:
    """Sanity: recover (~) planted theta, zeta from Bernoulli(P(fail|im))."""
    from scipy import stats

    rng = np.random.default_rng(42)
    theta_t, zeta_t = 0.45, 0.32
    n = 500
    im = np.exp(rng.normal(0, 0.5, size=n) + np.log(0.35))  # lognormal IM spread
    p = np.clip(
        stats.norm.cdf((np.log(im) - np.log(theta_t)) / zeta_t),
        1e-6,
        1.0 - 1e-6,
    )
    y = rng.binomial(1, p).astype(bool)
    fit = fit_lognormal_fragility_mle(FragilityData(im=im, failed=y))
    assert abs(np.log(fit.theta) - np.log(theta_t)) < 0.2
    assert abs(fit.zeta - zeta_t) < 0.12


def test_censored_mle_recovers_capacity_distribution() -> None:
    """
    Synthetic: ln(IM_c) ~ N(mu, beta^2); observed collapses are exact IM_c,
    censored samples only reveal IM_last < IM_c.
    """
    rng = np.random.default_rng(123)
    mu_t, beta_t = np.log(0.55), 0.35
    n = 600
    ln_cap = rng.normal(mu_t, beta_t, size=n)
    cap = np.exp(ln_cap)

    # Censoring: for a subset, we only observe last-tested = cap / exp(U)
    censored = rng.random(n) < 0.35
    u = rng.uniform(0.05, 0.8, size=n)  # ensure last-tested < cap
    im_obs = cap.copy()
    im_obs[censored] = cap[censored] / np.exp(u[censored])

    fit = fit_lognormal_capacity_censored_mle(im_obs, censored)
    assert abs(fit.mu - mu_t) < 0.08
    assert abs(fit.beta - beta_t) < 0.08
