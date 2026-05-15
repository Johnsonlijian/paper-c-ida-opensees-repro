from __future__ import annotations

from pathlib import Path

import pandas as pd

from paper_c_eesd.postprocess.collapse_and_mechanism import DemandRatioLimits
from paper_c_eesd.postprocess.pipeline import run_pipeline


def main() -> int:
    out_root = Path("data/demo")
    out_root.mkdir(parents=True, exist_ok=True)

    rows = []
    for specimen_id, drift_series in [
        ("A", [0.005, 0.012, 0.03]),  # collapse at last
        ("B", [0.005, 0.008, 0.010]),  # censored
        ("C", [0.005, 0.03, 0.05]),  # collapse earlier
        ("D", [0.005, 0.015, 0.019]),  # censored (just below limit)
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

    in_csv = out_root / "ida_raw_all.csv"
    pd.DataFrame(rows).to_csv(in_csv, index=False)

    limits = DemandRatioLimits(
        drift_limit=0.02,
        residual_drift_limit=0.01,
        steel_eps_t_limit=0.02,
        steel_eps_c_limit=-0.02,
        concrete_eps_c_limit=-0.01,
    )
    outs = run_pipeline(in_csv, out_dir=out_root, limits=limits, include_numerical=False)
    print("Outputs:", outs)
    print("\nMLE summary:")
    print(pd.read_csv(outs["mle_summary"]).to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

