"""
Lognormal fragility MLE (Baker 2015 style) for demand parameter IM.

    P(failure | IM) = Φ( (ln IM - ln θ) / ζ )

where θ is the median capacity in IM space and ζ is the **lognormal standard
deviation** (spread in ln-IM space). This is a **diagnostic** fit for Paper C;
β-decomposition consumes spread proxies from companion analyses.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np
from numpy.typing import NDArray
from scipy import optimize, stats

__all__ = [
    "FragilityData",
    "MLEFragilityLognormal",
    "CensoredLognormalFit",
    "fit_lognormal_fragility_mle",
    "fit_lognormal_capacity_censored_mle",
]


@dataclass
class FragilityData:
    im: NDArray[np.floating]
    failed: NDArray[np.bool_]

    def __post_init__(self) -> None:
        self.im = np.asarray(self.im, dtype=float)
        self.failed = np.asarray(self.failed, dtype=bool)
        if self.im.shape != self.failed.shape:
            raise ValueError("im and failed must have the same shape")
        if np.any(self.im <= 0):
            raise ValueError("IM must be positive for lognormal fragility.")


@dataclass(frozen=True, slots=True)
class MLEFragilityLognormal:
    theta: float  # median IM
    zeta: float  # lognormal std (ln-space spread)
    log_likelihood: float
    n: int
    result: Any = None  # raw scipy.optimize.OptimizeResult


@dataclass(frozen=True, slots=True)
class CensoredLognormalFit:
    """
    Fit ln(IM_c) ~ Normal(mu, beta^2) from observed + right-censored samples.

    - Observed samples: exact collapse IM values.
    - Censored samples: last-tested IM (capacity is > IM_last).
    """

    theta: float  # exp(mu)
    beta: float  # log-std in IM space (dispersion)
    mu: float
    log_likelihood: float
    n_total: int
    n_observed: int
    n_censored: int
    result: Any = None


def _neg_log_lik(p: NDArray[np.floating], im: NDArray, y: NDArray[np.bool_]) -> float:
    ln_theta, zeta = float(p[0]), float(p[1])
    if zeta <= 1e-9:
        return 1e12
    z = (np.log(im) - ln_theta) / zeta
    p_f = stats.norm.cdf(z)
    p_f = np.clip(p_f, 1e-12, 1.0 - 1e-12)
    ll = float(np.sum(np.where(y, np.log(p_f), np.log(1.0 - p_f))))
    return -ll


def fit_lognormal_fragility_mle(
    data: FragilityData,
    *,
    theta0: float | None = None,
    zeta0: float = 0.4,
) -> MLEFragilityLognormal:
    im = data.im
    y = data.failed
    n = int(im.size)
    if n < 5:
        raise ValueError("Need at least 5 data points for stable MLE.")
    t0 = float(np.median(im)) if theta0 is None else float(theta0)
    p0 = np.array([math.log(t0), zeta0], dtype=float)
    res = optimize.minimize(
        _neg_log_lik,
        p0,
        args=(im, y),
        method="L-BFGS-B",
        bounds=[(None, None), (1e-4, 5.0)],
    )
    if not res.success:
        raise RuntimeError(f"MLE did not converge: {res.message}")
    ln_t, zeta = float(res.x[0]), float(res.x[1])
    ll = -float(res.fun)
    return MLEFragilityLognormal(
        theta=math.exp(ln_t),
        zeta=zeta,
        log_likelihood=ll,
        n=n,
        result=res,
    )


def fit_lognormal_capacity_censored_mle(
    im_values: NDArray[np.floating],
    censored: NDArray[np.bool_],
    *,
    beta0: float = 0.35,
    min_beta: float = 1e-4,
    max_beta: float = 5.0,
) -> CensoredLognormalFit:
    """
    Right-censored MLE for collapse capacity IM.

    Model
    -----
        ln(IM_c) ~ Normal(mu, beta^2) , theta = exp(mu)

    Inputs
    ------
    im_values
        Observed: collapse IM.
        Censored: last-tested IM (IM_c > last-tested).
    censored
        True if right-censored.

    Notes
    -----
    - Requires at least 1 observed collapse to identify (mu, beta).
    - Uses log survival `norm.logsf` for numerical stability.
    """
    im = np.asarray(im_values, dtype=float)
    cen = np.asarray(censored, dtype=bool)
    if im.ndim != 1 or cen.ndim != 1 or im.shape[0] != cen.shape[0]:
        raise ValueError("im_values and censored must be 1D arrays of equal length.")
    if im.size < 2:
        raise ValueError("At least two observations are required.")
    if np.any(~np.isfinite(im)) or np.any(im <= 0):
        raise ValueError("im_values must be finite and positive.")

    obs = ~cen
    n_total = int(im.size)
    n_observed = int(obs.sum())
    n_censored = int(cen.sum())
    if n_observed == 0:
        raise ValueError(
            "All observations are right-censored; (mu, beta) not identifiable without an observed collapse."
        )

    y = np.log(im)
    # initial values from observed subset
    mu0 = float(np.mean(y[obs]))
    beta0 = float(np.std(y[obs], ddof=1)) if n_observed >= 2 else float(beta0)
    beta0 = float(np.clip(beta0, 0.15, max_beta))

    def neg_loglik(p: NDArray[np.floating]) -> float:
        mu = float(p[0])
        log_beta = float(p[1])
        beta = math.exp(log_beta)
        if beta < min_beta or beta > max_beta:
            return 1e12
        z = (y - mu) / beta
        ll_obs = stats.norm.logpdf(z[obs]) - log_beta
        ll_cen = stats.norm.logsf(z[cen])
        ll = float(np.sum(ll_obs) + np.sum(ll_cen))
        if not math.isfinite(ll):
            return 1e12
        return -ll

    res = optimize.minimize(
        neg_loglik,
        x0=np.array([mu0, math.log(beta0)], dtype=float),
        method="L-BFGS-B",
        bounds=[(None, None), (math.log(min_beta), math.log(max_beta))],
    )
    if not res.success:
        raise RuntimeError(f"Censored MLE did not converge: {res.message}")

    mu_hat = float(res.x[0])
    beta_hat = float(math.exp(float(res.x[1])))
    ll = -float(res.fun)
    return CensoredLognormalFit(
        theta=float(math.exp(mu_hat)),
        beta=beta_hat,
        mu=mu_hat,
        log_likelihood=ll,
        n_total=n_total,
        n_observed=n_observed,
        n_censored=n_censored,
        result=res,
    )
