from __future__ import annotations

"""
Run comparable pilot IDA subsets for FF22 and FFext.

Purpose:
- provide higher-quality evidence than a single-record demo
- keep runtime bounded
- produce directly plottable θ/β/censoring summaries
"""

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from paper_c_eesd.ida.run_single_opensees_tcl_ida import SingleTclRunConfig, run_single_opensees_tcl_ida
from paper_c_eesd.postprocess import collect_ida_raw_all, run_pipeline, validate_ida_raw_all_df
from paper_c_eesd.postprocess.collapse_and_mechanism import DemandRatioLimits


def _select_at2(manifest: pd.DataFrame, gm_set: str, n: int) -> pd.DataFrame:
    d = manifest[(manifest["gm_set"] == gm_set) & manifest["path"].astype(str).str.endswith(".AT2")].copy()
    # exclude verticals where naming makes that obvious
    d = d[~d["gm_id"].astype(str).str.contains("UP|--V", regex=True, case=False, na=False)]
    d = d.dropna(subset=["pga_g"]).sort_values("pga_g", ascending=False)
    # take reasonably strong but not only extremes: spread across sorted list
    if len(d) > n:
        idx = np.linspace(0, len(d) - 1, n).round().astype(int)
        d = d.iloc[idx]
    return d.head(n)


def _run_set(set_label: str, gm_rows: pd.DataFrame, *, out_root: Path, opensees_exe: Path) -> Path:
    runs_root = out_root / "runs" / set_label
    result_dir = out_root / "results" / set_label
    runs_root.mkdir(parents=True, exist_ok=True)
    result_dir.mkdir(parents=True, exist_ok=True)

    im_values = [0.2, 0.4, 0.6, 0.8, 1.0]
    for _, r in gm_rows.iterrows():
        gm_path = Path(str(r["path"]))
        gm_id = str(r["gm_id"])
        for im_level, im_value in enumerate(im_values):
            run_dir = runs_root / "S01" / gm_id / "P1" / "G1" / "SaT1" / f"{im_level:02d}"
            cfg = SingleTclRunConfig(
                specimen_id="S01",
                gm_id=gm_id,
                analysis_protocol_id="P1",
                im_grid_id="G1",
                im_type="SaT1",
                im_level=im_level,
                im_value=float(im_value),
                scale_factor=float(im_value),
                at2_path=gm_path,
                H=3.0,
                D=0.4,
                t_steel=0.008,
                opensees_exe=opensees_exe,
            )
            run_single_opensees_tcl_ida(run_dir, cfg)

    df = collect_ida_raw_all(runs_root)
    validate_ida_raw_all_df(df)
    ida_csv = result_dir / "ida_raw_all.csv"
    df.to_csv(ida_csv, index=False)

    limits = DemandRatioLimits(
        # pilot sensitivity threshold; documented as demo/pilot, not final design limit
        drift_limit=0.005,
        residual_drift_limit=0.01,
        steel_eps_t_limit=0.05,
        steel_eps_c_limit=-0.05,
        concrete_eps_c_limit=-0.008,
    )
    run_pipeline(ida_csv, out_dir=result_dir, limits=limits, include_numerical=False)
    return result_dir


def _plot_compare(result_dirs: dict[str, Path], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for label, rd in result_dirs.items():
        mle = pd.read_csv(rd / "censored_mle_summary.csv")
        all_row = mle[mle["group"] == "ALL"].iloc[0].to_dict()
        obs = pd.read_csv(rd / "collapse_observations.csv")
        all_row["set"] = label
        all_row["censoring_rate"] = float(obs["censored"].mean())
        rows.append(all_row)
    summ = pd.DataFrame(rows)
    summ.to_csv(out_dir / "pilot_set_comparison_summary.csv", index=False)

    fig, ax = plt.subplots(figsize=(7.0, 4.0))
    ax.bar(summ["set"], summ["theta"].fillna(0.0), color="#4C78A8")
    ax.set_ylabel("Median capacity θ (g)")
    ax.grid(True, axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(out_dir / "fig_compare_theta_ff22_ffext.png", dpi=200)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(7.0, 4.0))
    ax.bar(summ["set"], summ["censoring_rate"], color="#F58518")
    ax.set_ylabel("Censoring rate")
    ax.set_ylim(0, 1)
    ax.grid(True, axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(out_dir / "fig_compare_censoring_ff22_ffext.png", dpi=200)
    plt.close(fig)


def main() -> int:
    manifest = pd.read_csv("data/ground_motions/_derived/gm_manifest.csv")
    opensees_exe = Path("tools/opensees_bin/OpenSees3.8.0/bin/OpenSees.exe").resolve()
    if not opensees_exe.exists():
        raise SystemExit(f"OpenSees.exe not found: {opensees_exe}")

    out_root = Path("data/ida_compare_pilot")
    out_root.mkdir(parents=True, exist_ok=True)
    selected = {
        "FF22": _select_at2(manifest, "P695_FF22_AT2_original", 5),
        "FFext": _select_at2(manifest, "FFext_AT2_flat", 5),
    }
    for label, df in selected.items():
        df.to_csv(out_root / f"selected_{label}.csv", index=False)

    result_dirs = {
        label: _run_set(label, gm_rows, out_root=out_root, opensees_exe=opensees_exe)
        for label, gm_rows in selected.items()
    }
    _plot_compare(result_dirs, out_root / "figures")
    print("Wrote comparison to", out_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

