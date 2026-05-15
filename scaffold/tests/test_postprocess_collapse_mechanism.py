import numpy as np
import pandas as pd

from paper_c_eesd.postprocess import (
    DemandRatioLimits,
    add_collapse_flags,
    add_demand_ratios,
    add_first_crossing_and_censoring,
    add_triggers,
    assign_mechanism_label,
    build_collapse_observations,
)


def _base_df() -> pd.DataFrame:
    # Two groups: A collapses at level 2; B never collapses -> censored.
    rows = []
    for specimen_id, collapse_level in [("A", 2), ("B", None)]:
        for im_level, im_value in enumerate([0.2, 0.4, 0.6]):
            drift = 0.005 if collapse_level is None else (0.01 if im_level < collapse_level else 0.03)
            rows.append(
                {
                    "specimen_id": specimen_id,
                    "gm_id": "GM01",
                    "analysis_protocol_id": "P1",
                    "im_grid_id": "G1",
                    "im_type": "SaT1",
                    "im_level": im_level,
                    "im_value": im_value,
                    "converged": True,
                    "edp_max_drift_ratio": drift,
                    "edp_residual_drift_ratio": 0.0,
                    "steel_tube_eps_t_max": 0.0,
                    "steel_tube_eps_c_min": 0.0,
                    "concrete_core_eps_c_min": 0.0,
                }
            )
    return pd.DataFrame(rows)


def test_first_crossing_and_censoring_and_observations() -> None:
    df = _base_df()
    lim = DemandRatioLimits(
        drift_limit=0.02,
        residual_drift_limit=0.01,
        steel_eps_t_limit=0.02,
        steel_eps_c_limit=-0.02,
        concrete_eps_c_limit=-0.01,
    )
    df = add_demand_ratios(df, lim)
    df = add_collapse_flags(df, include_numerical=False)
    df = add_triggers(df)
    df = add_first_crossing_and_censoring(df)
    df["mechanism_label"] = assign_mechanism_label(df)

    # Group A: first crossing at im_value=0.6 (level 2)
    a = df[df["specimen_id"] == "A"].sort_values("im_value")
    assert a["first_crossing"].sum() == 1
    assert float(a[a["first_crossing"]].iloc[0]["im_value"]) == 0.6
    assert a["mechanism_label"].iloc[-1] == "flexural_drift"

    # Group B: censored at highest im_value=0.6
    b = df[df["specimen_id"] == "B"].sort_values("im_value")
    assert b["first_crossing"].sum() == 0
    assert b["censored"].sum() == 1
    assert bool(b.iloc[-1]["censored"]) is True

    obs = build_collapse_observations(df)
    assert set(obs["specimen_id"]) == {"A", "B"}
    a_obs = obs[obs["specimen_id"] == "A"].iloc[0]
    b_obs = obs[obs["specimen_id"] == "B"].iloc[0]
    assert np.isclose(float(a_obs["im_observation"]), 0.6)
    assert bool(a_obs["censored"]) is False
    assert np.isclose(float(b_obs["im_observation"]), 0.6)
    assert bool(b_obs["censored"]) is True

