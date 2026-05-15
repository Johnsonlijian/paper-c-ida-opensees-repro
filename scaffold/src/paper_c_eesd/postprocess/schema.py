"""
Implementation-stage schema definitions for Paper C.

We deliberately separate:
- run-level rows (specimen × GM × IM level): `ida_raw_all.csv`
- collapse-level rows (specimen × GM × protocol): `collapse_observations.csv`

The goal is reproducibility and lower post-processing complexity.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class IDARowSpec:
    """Minimal required columns for run-level IDA table."""

    # identifiers
    run_id: str
    specimen_id: str
    gm_id: str
    analysis_protocol_id: str
    im_grid_id: str

    # IM
    im_type: str
    im_level: int
    im_value: float
    scale_factor: float

    # status
    converged: bool
    analysis_status: str  # ok/nonconverged/...

    # EDPs (summary over time-history)
    edp_max_drift_ratio: float
    edp_residual_drift_ratio: float
    steel_tube_eps_t_max: float
    steel_tube_eps_c_min: float
    concrete_core_eps_c_min: float


@dataclass(frozen=True, slots=True)
class CollapseObsSpec:
    """One row per specimen×GM×protocol for censored MLE."""

    specimen_id: str
    gm_id: str
    analysis_protocol_id: str
    im_grid_id: str
    im_type: str
    im_observation: float  # collapse IM if observed else last-tested IM
    censored: bool

