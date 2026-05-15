"""
One-shot pipeline:

Level-0 `ida_raw_all.csv` (run-level)
  -> enriched Level-0 (demand ratios, collapse flags, first-crossing, mechanism)
  -> Level-1 `collapse_observations.csv` (collapse-level for censored MLE)
  -> censored MLE summaries (overall + by mechanism at first-crossing)
"""

from __future__ import annotations

import argparse
from dataclasses import asdict
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

from ..fragility.fit_fragility import fit_lognormal_capacity_censored_mle
from .collapse_and_mechanism import (
    DemandRatioLimits,
    add_collapse_flags,
    add_demand_ratios,
    add_first_crossing_and_censoring,
    add_triggers,
    assign_mechanism_label,
    build_collapse_observations,
)


def run_pipeline(
    ida_raw_all_csv: Path,
    *,
    out_dir: Path,
    limits: DemandRatioLimits,
    include_numerical: bool,
) -> dict[str, Path]:
    ida_raw_all_csv = Path(ida_raw_all_csv)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(ida_raw_all_csv)
    df = add_demand_ratios(df, limits)
    df = add_collapse_flags(df, include_numerical=include_numerical)
    df = add_triggers(df)
    df = add_first_crossing_and_censoring(df)
    df["mechanism_label"] = assign_mechanism_label(df)

    enriched_csv = out_dir / "ida_raw_all_enriched.csv"
    df.to_csv(enriched_csv, index=False)

    obs = build_collapse_observations(df)
    obs_csv = out_dir / "collapse_observations.csv"
    obs.to_csv(obs_csv, index=False)

    # Overall censored MLE on collapse observations. Small pilot subsets may be
    # all-censored; report diagnostics instead of failing the whole pipeline.
    n_total_all = int(len(obs))
    n_obs_all = int((~obs["censored"]).sum())
    n_cen_all = int(obs["censored"].sum())
    summaries = []
    try:
        fit_all = fit_lognormal_capacity_censored_mle(
            obs["im_observation"].to_numpy(dtype=float),
            obs["censored"].to_numpy(dtype=bool),
        )
        summaries.append(
            {
                "group": "ALL",
                "theta": fit_all.theta,
                "beta": fit_all.beta,
                "mu": fit_all.mu,
                "n_total": fit_all.n_total,
                "n_observed": fit_all.n_observed,
                "n_censored": fit_all.n_censored,
                "log_likelihood": fit_all.log_likelihood,
            }
        )
    except ValueError:
        summaries.append(
            {
                "group": "ALL",
                "theta": np.nan,
                "beta": np.nan,
                "mu": np.nan,
                "n_total": n_total_all,
                "n_observed": n_obs_all,
                "n_censored": n_cen_all,
                "log_likelihood": np.nan,
            }
        )

    # By mechanism: use first-crossing label per (spec,gm,protocol,grid,im_type)
    mech_map = (
        df[df["first_crossing"].astype(bool)]
        .sort_values(["specimen_id", "gm_id", "analysis_protocol_id", "im_grid_id", "im_type", "im_value"])
        .drop_duplicates(
            ["specimen_id", "gm_id", "analysis_protocol_id", "im_grid_id", "im_type"], keep="first"
        )[["specimen_id", "gm_id", "analysis_protocol_id", "im_grid_id", "im_type", "mechanism_label"]]
    )
    obs2 = obs.merge(
        mech_map,
        on=["specimen_id", "gm_id", "analysis_protocol_id", "im_grid_id", "im_type"],
        how="left",
    )
    obs2["mechanism_label"] = obs2["mechanism_label"].fillna("no_collapse_censored")

    for mech, g in obs2.groupby("mechanism_label", sort=True):
        n_total = int(len(g))
        n_obs = int((~g["censored"]).sum())
        n_cen = int(g["censored"].sum())
        # need >=2 points and at least one observed collapse; otherwise skip fit
        if n_total < 2 or n_obs == 0:
            summaries.append(
                {
                    "group": f"MECH::{mech}",
                    "theta": np.nan,
                    "beta": np.nan,
                    "mu": np.nan,
                    "n_total": n_total,
                    "n_observed": n_obs,
                    "n_censored": n_cen,
                    "log_likelihood": np.nan,
                }
            )
            continue
        fit = fit_lognormal_capacity_censored_mle(
            g["im_observation"].to_numpy(dtype=float),
            g["censored"].to_numpy(dtype=bool),
        )
        summaries.append(
            {
                "group": f"MECH::{mech}",
                "theta": fit.theta,
                "beta": fit.beta,
                "mu": fit.mu,
                "n_total": fit.n_total,
                "n_observed": fit.n_observed,
                "n_censored": fit.n_censored,
                "log_likelihood": fit.log_likelihood,
            }
        )

    summary_df = pd.DataFrame(summaries).sort_values("group")
    summary_csv = out_dir / "censored_mle_summary.csv"
    summary_df.to_csv(summary_csv, index=False)

    return {"enriched_level0": enriched_csv, "level1_obs": obs_csv, "mle_summary": summary_csv}


def _parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ida-raw-all-csv", type=Path, required=True)
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--include-numerical", action="store_true", help="Treat nonconverged as collapse")
    ap.add_argument("--drift-limit", type=float, default=0.02)
    ap.add_argument("--residual-drift-limit", type=float, default=0.01)
    ap.add_argument("--steel-eps-t-limit", type=float, default=0.02)
    ap.add_argument("--steel-eps-c-limit", type=float, default=-0.02)
    ap.add_argument("--concrete-eps-c-limit", type=float, default=-0.01)
    return ap.parse_args(list(argv) if argv is not None else None)


def main(argv: Iterable[str] | None = None) -> int:
    a = _parse_args(argv)
    limits = DemandRatioLimits(
        drift_limit=float(a.drift_limit),
        residual_drift_limit=float(a.residual_drift_limit),
        steel_eps_t_limit=float(a.steel_eps_t_limit),
        steel_eps_c_limit=float(a.steel_eps_c_limit),
        concrete_eps_c_limit=float(a.concrete_eps_c_limit),
    )
    out = run_pipeline(
        a.ida_raw_all_csv,
        out_dir=a.out_dir,
        limits=limits,
        include_numerical=bool(a.include_numerical),
    )
    print("Wrote:")
    for k, p in out.items():
        print(f"- {k}: {p}")
    print("Limits:", asdict(limits))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

