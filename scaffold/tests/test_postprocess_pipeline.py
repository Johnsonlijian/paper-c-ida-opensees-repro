from pathlib import Path

import numpy as np
import pandas as pd

from paper_c_eesd.postprocess import DemandRatioLimits, run_pipeline


def _make_level0_csv(p: Path) -> Path:
    # Two specimen groups. One collapses (drift) at higher IM, one censored.
    rows = []
    for specimen_id, drift_series in [
        ("A", [0.005, 0.012, 0.03]),  # crosses 0.02 at last point
        ("B", [0.005, 0.008, 0.010]),  # never crosses
    ]:
        for im_level, (im_value, drift) in enumerate(zip([0.2, 0.4, 0.6], drift_series)):
            rows.append(
                {
                    "run_id": f"{specimen_id}/GM01/P1/SaT1/{im_level}",
                    "specimen_id": specimen_id,
                    "gm_id": "GM01",
                    "analysis_protocol_id": "P1",
                    "im_grid_id": "G1",
                    "im_type": "SaT1",
                    "im_level": im_level,
                    "im_value": im_value,
                    "scale_factor": 1.0,
                    "converged": True,
                    "analysis_status": "ok",
                    "edp_max_drift_ratio": drift,
                    "edp_residual_drift_ratio": 0.0,
                    "steel_tube_eps_t_max": 0.0,
                    "steel_tube_eps_c_min": 0.0,
                    "concrete_core_eps_c_min": 0.0,
                }
            )
    df = pd.DataFrame(rows)
    p.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(p, index=False)
    return p


def test_pipeline_writes_outputs_and_mle_summary(tmp_path: Path) -> None:
    in_csv = _make_level0_csv(tmp_path / "ida_raw_all.csv")
    out_dir = tmp_path / "out"
    limits = DemandRatioLimits(
        drift_limit=0.02,
        residual_drift_limit=0.01,
        steel_eps_t_limit=0.02,
        steel_eps_c_limit=-0.02,
        concrete_eps_c_limit=-0.01,
    )
    outputs = run_pipeline(in_csv, out_dir=out_dir, limits=limits, include_numerical=False)
    for p in outputs.values():
        assert Path(p).exists()

    obs = pd.read_csv(outputs["level1_obs"])
    assert len(obs) == 2
    # A observed collapse at 0.6, B censored at 0.6
    a = obs[obs["specimen_id"] == "A"].iloc[0]
    b = obs[obs["specimen_id"] == "B"].iloc[0]
    assert np.isclose(float(a["im_observation"]), 0.6)
    assert bool(a["censored"]) is False
    assert np.isclose(float(b["im_observation"]), 0.6)
    assert bool(b["censored"]) is True

    summ = pd.read_csv(outputs["mle_summary"])
    assert "group" in summ.columns
    assert (summ["group"] == "ALL").any()

