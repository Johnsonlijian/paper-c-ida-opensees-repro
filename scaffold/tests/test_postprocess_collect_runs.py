import json
from pathlib import Path

import pandas as pd

from paper_c_eesd.postprocess import collect_ida_raw_all, validate_ida_raw_all_df


def _write_json(p: Path, obj: dict) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def test_collect_runs_builds_level0_table(tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"
    # create 2 runs
    for i, im_value in enumerate([0.2, 0.4]):
        rd = runs_root / f"run_{i:03d}"
        _write_json(
            rd / "run_meta.json",
            {
                "specimen_id": "S01",
                "gm_id": "GM01",
                "analysis_protocol_id": "P1",
                "im_grid_id": "G1",
                "im_type": "SaT1",
                "im_level": i,
                "im_value": im_value,
                "scale_factor": 1.0 + i,
                "converged": True,
                "analysis_status": "ok",
            },
        )
        _write_json(
            rd / "edp_summary.json",
            {
                "edp_max_drift_ratio": 0.01 * (i + 1),
                "edp_residual_drift_ratio": 0.0,
                "steel_tube_eps_t_max": 0.0,
                "steel_tube_eps_c_min": 0.0,
                "concrete_core_eps_c_min": 0.0,
            },
        )

    df = collect_ida_raw_all(runs_root)
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 2
    validate_ida_raw_all_df(df)
    assert set(df["im_value"].tolist()) == {0.2, 0.4}

