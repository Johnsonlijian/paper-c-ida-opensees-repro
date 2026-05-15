"""
Post-process run-level `ida_raw_all.csv` into:
- collapse-level observations for censored MLE
- first-crossing flags
- mechanism labels via max demand-ratio rule

This module is intentionally pure-Python and does not depend on OpenSees.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Literal

import numpy as np
import pandas as pd

MechanismLabel = Literal[
    "flexural_drift",
    "residual_drift",
    "material_instability",
    "no_collapse_censored",
    "mixed",
]


@dataclass(frozen=True, slots=True)
class DemandRatioLimits:
    drift_limit: float
    residual_drift_limit: float
    steel_eps_t_limit: float
    steel_eps_c_limit: float
    concrete_eps_c_limit: float


def _safe_abs(x: float) -> float:
    return float(abs(x))


def add_demand_ratios(df: pd.DataFrame, limits: DemandRatioLimits) -> pd.DataFrame:
    out = df.copy()
    out["dr_drift"] = out["edp_max_drift_ratio"] / limits.drift_limit
    out["dr_residual"] = out["edp_residual_drift_ratio"] / limits.residual_drift_limit
    out["dr_steel_t"] = out["steel_tube_eps_t_max"] / limits.steel_eps_t_limit
    out["dr_steel_c"] = out["steel_tube_eps_c_min"].abs() / _safe_abs(limits.steel_eps_c_limit)
    out["dr_concrete_c"] = out["concrete_core_eps_c_min"].abs() / _safe_abs(limits.concrete_eps_c_limit)
    return out


def add_collapse_flags(df: pd.DataFrame, *, include_numerical: bool) -> pd.DataFrame:
    """
    Collapse rule:
    - EDP exceedance: any dr_* >= 1
    - Optionally numerical: nonconverged run counts as collapse
    """
    out = df.copy()
    edp_collapse = (
        (out["dr_drift"] >= 1)
        | (out["dr_residual"] >= 1)
        | (out["dr_steel_t"] >= 1)
        | (out["dr_steel_c"] >= 1)
        | (out["dr_concrete_c"] >= 1)
    )
    out["collapse_edp"] = edp_collapse
    out["collapse_num_or_edp"] = edp_collapse | (~out["converged"]) if include_numerical else edp_collapse
    return out


def _max_trigger(row: pd.Series) -> tuple[str, float]:
    mapping = {
        "drift": float(row["dr_drift"]),
        "residual": float(row["dr_residual"]),
        "steel_t": float(row["dr_steel_t"]),
        "steel_c": float(row["dr_steel_c"]),
        "concrete": float(row["dr_concrete_c"]),
    }
    k = max(mapping, key=mapping.get)
    return k, mapping[k]


def add_triggers(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    triggers = out.apply(_max_trigger, axis=1, result_type="expand")
    out["collapse_trigger"] = triggers[0]
    out["collapse_trigger_value"] = triggers[1]
    return out


def add_first_crossing_and_censoring(
    df: pd.DataFrame,
    *,
    group_cols: Iterable[str] = ("specimen_id", "gm_id", "analysis_protocol_id", "im_grid_id", "im_type"),
    im_col: str = "im_value",
    collapse_col: str = "collapse_edp",
) -> pd.DataFrame:
    """
    Adds:
    - is_highest_im_level
    - first_crossing (first row where collapse_col is True)
    - censored (highest row when no crossing)
    """
    out = df.copy()
    out = out.sort_values(list(group_cols) + [im_col])
    out["is_highest_im_level"] = False
    out["first_crossing"] = False
    out["censored"] = False

    for _, g in out.groupby(list(group_cols), sort=False):
        idxs = g.index.to_list()
        if not idxs:
            continue
        out.loc[idxs[-1], "is_highest_im_level"] = True
        crossed = g[g[collapse_col].astype(bool)]
        if len(crossed) > 0:
            out.loc[crossed.index[0], "first_crossing"] = True
        else:
            out.loc[idxs[-1], "censored"] = True
    return out


def assign_mechanism_label(df: pd.DataFrame, *, collapse_col: str = "collapse_edp") -> pd.Series:
    """
    Mechanism label:
    - if censored (no collapse): no_collapse_censored
    - else at first-crossing row: label is argmax of demand ratios
    """
    labels: list[str] = []
    for _i, r in df.iterrows():
        if bool(r.get("censored", False)) and bool(r.get("is_highest_im_level", False)):
            labels.append("no_collapse_censored")
            continue
        if not bool(r.get("first_crossing", False)):
            labels.append("")
            continue
        k, _ = _max_trigger(r)
        if k in ("drift",):
            labels.append("flexural_drift")
        elif k in ("residual",):
            labels.append("residual_drift")
        else:
            labels.append("material_instability")
    return pd.Series(labels, index=df.index, name="mechanism_label")


def build_collapse_observations(df: pd.DataFrame) -> pd.DataFrame:
    """
    One row per group (spec×gm×protocol×grid×im_type):
    - if first_crossing exists: im_observation = im_value at first_crossing, censored=False
    - else: im_observation = im_value at highest level, censored=True
    """
    req = ["specimen_id", "gm_id", "analysis_protocol_id", "im_grid_id", "im_type", "im_value", "first_crossing"]
    missing = [c for c in req if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    out_rows = []
    group_cols = ["specimen_id", "gm_id", "analysis_protocol_id", "im_grid_id", "im_type"]
    d = df.sort_values(group_cols + ["im_value"])
    for keys, g in d.groupby(group_cols, sort=False):
        first = g[g["first_crossing"].astype(bool)]
        if len(first) > 0:
            im_obs = float(first.iloc[0]["im_value"])
            cens = False
        else:
            im_obs = float(g.iloc[-1]["im_value"])
            cens = True
        row = dict(zip(group_cols, keys))
        row["im_observation"] = im_obs
        row["censored"] = cens
        out_rows.append(row)
    return pd.DataFrame(out_rows)

