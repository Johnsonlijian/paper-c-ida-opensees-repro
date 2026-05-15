"""
Core novelty (Paper C): orthogonal decomposition in standard-normal / β index space
for performance-based epistemic taxonomy, with an *explicit* evaluation-protocol
component (β_eval) on the same footing as more familiar model / record / statistical terms.

**Mathematical convention**
For independent, zero-mean Gaussian *pieces* in log-capacity, log-IM, or
standardised demand–capacity **spread** (each reported as a non-negative scalar
*β-k-style* component in a reliability sense), the total (when mechanisms are
orthogonal) satisfies:

    β_total² = Σ_i β_i²  (Pythagorean in β-space)

When two *protocol* estimates of the same *structured* system exist — one
optimistic (e.g. capacity pipeline trained with implicit leakage) and one
strict (e.g. grouped withholding) — the **excess** in β-space, under
orthogonality between the strict core and the *evaluation* artifact, is:

    β_eval = sqrt( max(0, β_optimistic² − β_strict²) )

This module implements these identities without importing fragility MLE, so
pure unit tests and synthetic generators stay lightweight.

References
----------
Baker, J.W. (2015) Fitting fragility functions to data. (implementation companion: MLE
    in `fit_fragility.py`).

Caution
-------
Orthogonality is a working **first-order** assumption for manuscript framing;
sensitivity to correlation belongs in the Discussion, not in these helpers.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, Iterator, Mapping

__all__ = [
    "BetaDecomposition",
    "InflationResult",
    "compose_independent_betas",
    "decompose_inflation_orthogonal",
    "pythagorean_check",
    "iter_component_triples",
]


def _nonneg(name: str, v: float) -> float:
    if v < 0 or not math.isfinite(v):
        raise ValueError(f"{name} must be a finite non-negative number, got {v!r}")
    return v


def compose_independent_betas(components: Mapping[str, float]) -> float:
    """
    Pythagorean sum in β-space: sqrt(sum β_i^2) for *orthogonal* non-negative parts.

    Parameters
    ----------
    components
        Named pieces (e.g. ``record_to_record``, ``model`` , ``statistical`` , ``eval_protocol``).
    """
    s = 0.0
    for k, b in components.items():
        b = _nonneg(k, float(b))
        s += b * b
    return math.sqrt(s)


@dataclass(frozen=True, slots=True)
class InflationResult:
    """Result of a strict/optimistic β pair decomposition."""

    beta_optimistic: float
    beta_strict: float
    beta_excess: float
    method: str = "orthogonal_inflation"
    # residual when optimistic is too small (correlation, mis-spec, re-labelling)
    flags: tuple[str, ...] = ()


def decompose_inflation_orthogonal(
    beta_optimistic: float,
    beta_strict: float,
) -> InflationResult:
    """
    Compute β_eval = sqrt(max(0, bo² − bs²)) when the optimistic number includes
    an *additional* independent variance-like component w.r.t. the stricter
    (honest) protocol, both already expressed in compatible β components.

    - If `beta_optimistic` < `beta_strict`, the excess is **0** and
      ``("optimistic_lt_strict",)`` is set in `flags` (warrants diagnosis, not NaN).
    """
    bo = _nonneg("beta_optimistic", float(beta_optimistic))
    bs = _nonneg("beta_strict", float(beta_strict))
    if bo * bo < bs * bs:
        return InflationResult(
            beta_optimistic=bo,
            beta_strict=bs,
            beta_excess=0.0,
            flags=("optimistic_lt_strict",),
        )
    return InflationResult(
        beta_optimistic=bo,
        beta_strict=bs,
        beta_excess=math.sqrt(bo * bo - bs * bs),
    )


@dataclass
class BetaDecomposition:
    """
    Named registry for a PBEE-side uncertainty *taxonomy* row.

    ``components`` is the mutable working dict; :meth:`register` and :meth:`total`
    keep Pythagorean sum consistent. **β_eval** (evaluation protocol) is a first-class key.
    """

    components: Dict[str, float] = field(default_factory=dict)

    def register(self, name: str, beta: float) -> None:
        self.components[name] = _nonneg(name, float(beta))

    def total(self) -> float:
        return compose_independent_betas(self.components)

    def with_eval_protocol_inflation(
        self,
        beta_optimistic: float,
        beta_strict: float,
        name_excess: str = "eval_protocol",
    ) -> tuple["BetaDecomposition", InflationResult]:
        """
        Return a new registry with the evaluation excess term from an optimistic/strict
        pair, and the :class:`InflationResult` for logging (flags, etc.).
        """
        r = decompose_inflation_orthogonal(beta_optimistic, beta_strict)
        b = BetaDecomposition(components=dict(self.components))
        b.register(name_excess, r.beta_excess)
        return b, r

    def __iter__(self) -> Iterator[tuple[str, float]]:
        yield from self.components.items()


def pythagorean_check(components: Mapping[str, float], total: float, *, rtol: float = 1e-9) -> bool:
    """``True`` if `total` ≈ ``compose_independent_betas(components)`` (relative tolerance)."""
    c = compose_independent_betas(components)
    t = float(total)
    if c == 0.0 and t == 0.0:
        return True
    return abs(c - t) <= rtol * (abs(c) + abs(t)) + 1e-15


def iter_component_triples(components: Mapping[str, float]) -> Iterator[tuple[str, float, float]]:
    """
    Yields (name, beta_i, fraction_of_rss) with fraction = β_i²/β_total², for GSA-style reporting.
    """
    tot2 = 0.0
    bmap = {k: _nonneg(k, float(v)) for k, v in components.items()}
    for b in bmap.values():
        tot2 += b * b
    if tot2 == 0.0:
        return
    for k, b in bmap.items():
        yield k, b, (b * b) / tot2
