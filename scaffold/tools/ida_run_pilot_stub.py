from __future__ import annotations

"""
Pilot runner (stub): generates run directories, runs OpenSeesPy, then computes
Level-0/Level-1/MLE outputs.

This script is intentionally conservative: it runs a small subset and is meant
to be adapted to your real specimen table and ground motions directory.
"""

from pathlib import Path

from paper_c_eesd.ida.run_single_opensees_tcl_ida import SingleTclRunConfig, run_single_opensees_tcl_ida
from paper_c_eesd.postprocess import collect_ida_raw_all, run_pipeline, validate_ida_raw_all_df
from paper_c_eesd.postprocess.collapse_and_mechanism import DemandRatioLimits


def main() -> int:
    # User must place AT2 files here (from configs/default.yaml)
    at2_dir = Path("data/ground_motions")
    at2_files = sorted(at2_dir.glob("**/*.AT2"))
    if not at2_files:
        raise SystemExit("No AT2 files found under data/ground_motions. Add a few *.AT2 to run pilot.")

    runs_root = Path("data/ida_runs_pilot")
    out_dir = Path("data/ida_results_pilot")
    runs_root.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Minimal demo specimen
    specimen_id = "S01"
    H, D, t = 3.0, 0.4, 0.008

    opensees_exe = Path(
        "tools/opensees_bin/OpenSees3.8.0/bin/OpenSees.exe"
    ).resolve()
    if not opensees_exe.exists():
        raise SystemExit(f"OpenSees.exe not found: {opensees_exe}")

    # Run a tiny set: 1 specimen × 2 GMs × 3 IM levels (needs >=2 obs for censored MLE)
    for gm_path in at2_files[:2]:
        gm_id = gm_path.stem
        for im_level, im_value in enumerate([0.2, 0.4, 0.6]):
            run_dir = runs_root / specimen_id / gm_id / "P1" / "G1" / "SaT1" / f"{im_level:02d}"
            cfg = SingleTclRunConfig(
                specimen_id=specimen_id,
                gm_id=gm_id,
                analysis_protocol_id="P1",
                im_grid_id="G1",
                im_type="SaT1",
                im_level=im_level,
                im_value=float(im_value),
                scale_factor=float(im_value),  # placeholder scaling
                at2_path=gm_path,
                H=H,
                D=D,
                t_steel=t,
                opensees_exe=opensees_exe,
            )
            run_single_opensees_tcl_ida(run_dir, cfg)

    # Level-0 table
    df = collect_ida_raw_all(runs_root)
    validate_ida_raw_all_df(df)
    ida_csv = out_dir / "ida_raw_all.csv"
    df.to_csv(ida_csv, index=False)

    # Level-1 + MLE
    limits = DemandRatioLimits(
        # NOTE: for the demo cantilever model, use a small drift limit so we observe at least
        # one collapse in a tiny pilot run (otherwise all observations are censored and MLE is
        # not identifiable).
        drift_limit=0.005,
        residual_drift_limit=0.01,
        steel_eps_t_limit=0.05,
        steel_eps_c_limit=-0.05,
        concrete_eps_c_limit=-0.008,
    )
    run_pipeline(ida_csv, out_dir=out_dir, limits=limits, include_numerical=False)
    print("Wrote outputs to", out_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

