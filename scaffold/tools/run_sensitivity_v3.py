from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from paper_c_eesd.ida.run_single_opensees_tcl_ida import SingleTclRunConfig, run_single_opensees_tcl_ida
from paper_c_eesd.postprocess import collect_ida_raw_all, run_pipeline, validate_ida_raw_all_df
from paper_c_eesd.postprocess.collapse_and_mechanism import DemandRatioLimits


IM_VALUES = [round(x, 1) for x in np.arange(0.1, 1.21, 0.1)]
PROTOCOL = "P1"
OUT_ROOT = Path("data/sensitivity_v3")
MANUSCRIPT_FIG_DIR = Path("docs/manuscript_drafts/figures")


def _select_by_pga_span(df: pd.DataFrame, n: int) -> pd.DataFrame:
    d = df.dropna(subset=["pga_g"]).sort_values("pga_g", ascending=False).reset_index(drop=True)
    if len(d) <= n:
        return d.copy()
    idx = np.linspace(0, len(d) - 1, n).round().astype(int)
    return d.iloc[idx].copy()


def _select_at2(manifest: pd.DataFrame, gm_set: str, n: int) -> pd.DataFrame:
    d = manifest[(manifest["gm_set"] == gm_set) & manifest["path"].astype(str).str.endswith(".AT2")].copy()
    d = d[~d["gm_id"].astype(str).str.contains("UP|--V", regex=True, case=False, na=False)]
    out = _select_by_pga_span(d, n)
    out["record_set"] = "FF22" if gm_set == "P695_FF22_AT2_original" else "FFext"
    return out


def _select_nf28(nf_manifest: pd.DataFrame, n: int) -> pd.DataFrame:
    d = nf_manifest[nf_manifest["ready_for_time_history"].astype(bool)].copy()
    d = d.dropna(subset=["base_eq_id", "pga_g"])
    d = d.sort_values("pga_g", ascending=False).drop_duplicates(subset=["base_eq_id"], keep="first")
    out = _select_by_pga_span(d, n)
    out["record_set"] = "NF28"
    return out


def _limits_from_specimens(specimens: pd.DataFrame) -> DemandRatioLimits:
    r = specimens.iloc[0]
    return DemandRatioLimits(
        drift_limit=float(r["drift_limit"]),
        residual_drift_limit=float(r["residual_drift_limit"]),
        steel_eps_t_limit=float(r["steel_eps_t_limit"]),
        steel_eps_c_limit=float(r["steel_eps_c_limit"]),
        concrete_eps_c_limit=float(r["concrete_eps_c_limit"]),
    )


def _run_is_complete(run_dir: Path) -> bool:
    return (run_dir / "run_meta.json").exists() and (run_dir / "edp_summary.json").exists()


def _run_matrix(
    *,
    set_label: str,
    gm_rows: pd.DataFrame,
    specimens: pd.DataFrame,
    out_root: Path,
    opensees_exe: Path,
) -> Path:
    runs_root = out_root / "runs" / set_label / PROTOCOL
    result_dir = out_root / "results" / set_label / PROTOCOL
    runs_root.mkdir(parents=True, exist_ok=True)
    result_dir.mkdir(parents=True, exist_ok=True)

    n_total = len(specimens) * len(gm_rows) * len(IM_VALUES)
    n_done = 0
    n_skipped = 0
    for _, sp in specimens.iterrows():
        specimen_id = str(sp["specimen_id"])
        for _, gm in gm_rows.iterrows():
            gm_path = Path(str(gm["path"]))
            gm_id = str(gm["gm_id"])
            for im_level, im_value in enumerate(IM_VALUES):
                run_dir = runs_root / specimen_id / gm_id / PROTOCOL / "G3fine" / "SaT1" / f"{im_level:02d}"
                if _run_is_complete(run_dir):
                    n_skipped += 1
                    continue
                cfg = SingleTclRunConfig(
                    specimen_id=specimen_id,
                    gm_id=gm_id,
                    analysis_protocol_id=PROTOCOL,
                    im_grid_id="G3fine",
                    im_type="SaT1",
                    im_level=im_level,
                    im_value=float(im_value),
                    scale_factor=float(im_value),
                    at2_path=gm_path,
                    H=float(sp["H"]),
                    D=float(sp["D"]),
                    t_steel=float(sp["t_steel"]),
                    opensees_exe=opensees_exe,
                )
                run_single_opensees_tcl_ida(run_dir, cfg)
                n_done += 1
    print(f"{set_label}-{PROTOCOL}: ran {n_done}, skipped {n_skipped}, expected {n_total}")

    df = collect_ida_raw_all(runs_root)
    validate_ida_raw_all_df(df)
    ida_csv = result_dir / "ida_raw_all.csv"
    df.to_csv(ida_csv, index=False)

    run_pipeline(
        ida_csv,
        out_dir=result_dir,
        limits=_limits_from_specimens(specimens),
        include_numerical=False,
    )
    return result_dir


def _collect_summary(result_dirs: dict[str, Path], out_dir: Path) -> pd.DataFrame:
    rows = []
    for set_label, rd in sorted(result_dirs.items()):
        mle = pd.read_csv(rd / "censored_mle_summary.csv")
        all_row = mle[mle["group"] == "ALL"].iloc[0].to_dict()
        obs = pd.read_csv(rd / "collapse_observations.csv")
        raw = pd.read_csv(rd / "ida_raw_all.csv")
        enriched = pd.read_csv(rd / "ida_raw_all_enriched.csv")
        all_row["record_set"] = set_label
        all_row["protocol"] = PROTOCOL
        all_row["censoring_rate"] = float(obs["censored"].mean())
        all_row["n_runs"] = int(len(raw))
        all_row["n_nonconverged"] = int((~raw["converged"].astype(bool)).sum())
        all_row["n_first_crossing"] = int(enriched["first_crossing"].astype(bool).sum())
        rows.append(all_row)
    summary = pd.DataFrame(rows)
    out_dir.mkdir(parents=True, exist_ok=True)
    summary.to_csv(out_dir / "sensitivity_v3_summary.csv", index=False)
    return summary


def _make_protocol_ledger(summary: pd.DataFrame, out_dir: Path) -> pd.DataFrame:
    ref = summary[summary["record_set"] == "FF22"].iloc[0]
    theta_ref = float(ref["theta"])
    rows = []
    for _, row in summary.sort_values("record_set").iterrows():
        theta = float(row["theta"])
        log_shift = float(np.log(theta / theta_ref))
        rows.append(
            {
                "effect_family": "record_pool_grid_refined",
                "reference_record_set": "FF22",
                "record_set": row["record_set"],
                "protocol": PROTOCOL,
                "theta_ref": theta_ref,
                "theta": theta,
                "theta_percent_shift_vs_ref": 100.0 * (theta - theta_ref) / theta_ref,
                "log_theta_shift_vs_ref": log_shift,
                "beta_pool_equiv_binary": abs(log_shift) / 2.0,
                "beta": float(row["beta"]),
                "censoring_rate": float(row["censoring_rate"]),
                "n_runs": int(row["n_runs"]),
                "n_nonconverged": int(row["n_nonconverged"]),
            }
        )
    ledger = pd.DataFrame(rows)
    ledger.to_csv(out_dir / "sensitivity_v3_protocol_effect_ledger.csv", index=False)
    return ledger


def _plot_summary(summary: pd.DataFrame, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    MANUSCRIPT_FIG_DIR.mkdir(parents=True, exist_ok=True)
    summary = summary.sort_values("record_set").copy()
    fig, axes = plt.subplots(1, 3, figsize=(11.5, 3.5))
    for ax, (col, ylabel, color) in zip(
        axes,
        [
            ("theta", r"Median capacity $\theta$ (g)", "#4C78A8"),
            ("beta", r"Dispersion $\beta$", "#72B7B2"),
            ("censoring_rate", "Censoring rate", "#F58518"),
        ],
    ):
        ax.bar(summary["record_set"], summary[col], color=color)
        ax.set_ylabel(ylabel)
        ax.grid(True, axis="y", alpha=0.25)
    fig.suptitle("Sensitivity v3: 10 records per pool, fine IM grid, P1 only", fontweight="bold", y=1.03)
    fig.tight_layout()
    fig.savefig(out_dir / "fig_sensitivity_v3_summary.png", dpi=300, bbox_inches="tight")
    fig.savefig(MANUSCRIPT_FIG_DIR / "fig8_sensitivity_v3_summary.png", dpi=300, bbox_inches="tight")
    plt.close(fig)


def _write_note(summary: pd.DataFrame, ledger: pd.DataFrame, out_dir: Path) -> None:
    p1 = summary.set_index("record_set")
    lines = [
        "# Sensitivity v3 Summary",
        "",
        "Matrix: 5 specimens x 10 records per pool x 12 IM levels x 3 record pools x P1 = 1800 OpenSees runs.",
        "",
        "## Fragility estimates",
        "",
    ]
    for record_set in ["FF22", "FFext", "NF28"]:
        if record_set in p1.index:
            r = p1.loc[record_set]
            lines.append(
                f"- {record_set}: theta={float(r['theta']):.4f} g, beta={float(r['beta']):.4f}, "
                f"censoring={float(r['censoring_rate']):.2%}, nonconverged={int(r['n_nonconverged'])}."
            )
    lines.extend(["", "## Protocol-effect ledger", ""])
    for _, row in ledger.iterrows():
        lines.append(
            f"- {row['record_set']} vs FF22: theta shift={row['theta_percent_shift_vs_ref']:+.1f}%, "
            f"log shift={row['log_theta_shift_vs_ref']:+.3f}, beta_pool={row['beta_pool_equiv_binary']:.3f}."
        )
    (out_dir / "sensitivity_v3_results_note.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    fig_dir = OUT_ROOT / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)
    manifest = pd.read_csv("data/ground_motions/_derived/gm_manifest.csv")
    nf_manifest = pd.read_csv("data/ground_motions/_derived/nf28_sorted_manifest.csv")
    specimens = pd.read_csv("data/specimen_table_pilot_v1.csv")
    opensees_exe = Path("tools/opensees_bin/OpenSees3.8.0/bin/OpenSees.exe").resolve()
    if not opensees_exe.exists():
        raise SystemExit(f"OpenSees.exe not found: {opensees_exe}")

    selected = {
        "FF22": _select_at2(manifest, "P695_FF22_AT2_original", 10),
        "FFext": _select_at2(manifest, "FFext_AT2_flat", 10),
        "NF28": _select_nf28(nf_manifest, 10),
    }
    for label, df in selected.items():
        df.to_csv(OUT_ROOT / f"selected_{label}.csv", index=False)

    result_dirs: dict[str, Path] = {}
    for set_label, gm_rows in selected.items():
        result_dirs[set_label] = _run_matrix(
            set_label=set_label,
            gm_rows=gm_rows,
            specimens=specimens,
            out_root=OUT_ROOT,
            opensees_exe=opensees_exe,
        )
    summary = _collect_summary(result_dirs, fig_dir)
    ledger = _make_protocol_ledger(summary, fig_dir)
    _plot_summary(summary, fig_dir)
    _write_note(summary, ledger, fig_dir)
    print("Wrote sensitivity v3 to", OUT_ROOT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

