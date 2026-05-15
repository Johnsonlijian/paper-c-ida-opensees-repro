from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from paper_c_eesd.ida.run_single_opensees_tcl_ida import SingleTclRunConfig, run_single_opensees_tcl_ida
from paper_c_eesd.postprocess import collect_ida_raw_all, run_pipeline, validate_ida_raw_all_df
from paper_c_eesd.postprocess.collapse_and_mechanism import DemandRatioLimits


RECORD_SETS = ["FF22", "FFext", "NF28"]
PROTOCOL = "P1"
COARSE_IM_VALUES = [0.2, 0.4, 0.6, 0.8, 1.0]
FINE_IM_VALUES = [round(x, 1) for x in np.arange(0.1, 1.21, 0.1)]

SOURCE_V2 = Path("data/expanded_pilot_v2")
SOURCE_V3 = Path("data/sensitivity_v3")
OUT_ROOT = Path("data/protocol_split_r34")
RUN_ROOT = Path("data/r34split_runs")
FIG_DIR = OUT_ROOT / "figures"
MANUSCRIPT_FIG_DIR = Path("docs/manuscript_drafts/figures")

SCENARIO_ORDER = [
    "v2_N5_G5_existing",
    "r34_N5_G12_v2_records",
    "r34_N10_G5_v3_records",
    "v3_N10_G12_existing",
]


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


def _selected_v2_records(record_set: str) -> pd.DataFrame:
    path = SOURCE_V2 / f"selected_{record_set}.csv"
    if not path.exists():
        raise FileNotFoundError(path)
    return pd.read_csv(path)


def _write_selection_overlap_note() -> pd.DataFrame:
    rows = []
    for record_set in RECORD_SETS:
        v2 = pd.read_csv(SOURCE_V2 / f"selected_{record_set}.csv")
        v3 = pd.read_csv(SOURCE_V3 / f"selected_{record_set}.csv")
        v2_ids = set(v2["gm_id"].astype(str))
        v3_ids = set(v3["gm_id"].astype(str))
        rows.append(
            {
                "record_set": record_set,
                "v2_n_records": int(len(v2_ids)),
                "v3_n_records": int(len(v3_ids)),
                "overlap_n": int(len(v2_ids & v3_ids)),
                "overlap_gm_ids": ";".join(sorted(v2_ids & v3_ids)),
                "v2_only_gm_ids": ";".join(sorted(v2_ids - v3_ids)),
                "v3_only_gm_ids": ";".join(sorted(v3_ids - v2_ids)),
            }
        )
    out = pd.DataFrame(rows)
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT_ROOT / "r34_v2_v3_record_selection_overlap.csv", index=False)
    return out


def _run_n5_g12_v2_records(*, specimens: pd.DataFrame, limits: DemandRatioLimits, opensees_exe: Path) -> dict[str, Path]:
    scenario = "r34_N5_G12_v2_records"
    scenario_short = "N5G12"
    result_dirs: dict[str, Path] = {}
    for record_set in RECORD_SETS:
        gm_rows = _selected_v2_records(record_set)
        # Keep run paths short on Windows so recorder filenames such as
        # steel_strain_0.out stay well below MAX_PATH.
        runs_root = RUN_ROOT / scenario_short / record_set
        result_dir = OUT_ROOT / "results" / scenario / record_set / PROTOCOL
        runs_root.mkdir(parents=True, exist_ok=True)
        result_dir.mkdir(parents=True, exist_ok=True)

        n_total = len(specimens) * len(gm_rows) * len(FINE_IM_VALUES)
        n_done = 0
        n_skipped = 0
        for _, sp in specimens.iterrows():
            specimen_id = str(sp["specimen_id"])
            for _, gm in gm_rows.iterrows():
                gm_path = Path(str(gm["path"]))
                gm_id = str(gm["gm_id"])
                for im_level, im_value in enumerate(FINE_IM_VALUES):
                    run_dir = (
                        runs_root
                        / specimen_id
                        / gm_id
                        / f"{im_level:02d}"
                    )
                    if _run_is_complete(run_dir):
                        n_skipped += 1
                        continue
                    cfg = SingleTclRunConfig(
                        specimen_id=specimen_id,
                        gm_id=gm_id,
                        analysis_protocol_id=PROTOCOL,
                        im_grid_id="G3fine_v2records",
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

        print(f"{scenario}-{record_set}-{PROTOCOL}: ran {n_done}, skipped {n_skipped}, expected {n_total}")
        raw = collect_ida_raw_all(runs_root)
        validate_ida_raw_all_df(raw)
        raw_csv = result_dir / "ida_raw_all.csv"
        raw.to_csv(raw_csv, index=False)
        run_pipeline(raw_csv, out_dir=result_dir, limits=limits, include_numerical=False)
        result_dirs[record_set] = result_dir
    return result_dirs


def _filter_n10_g5_from_v3(*, limits: DemandRatioLimits) -> dict[str, Path]:
    scenario = "r34_N10_G5_v3_records"
    result_dirs: dict[str, Path] = {}
    for record_set in RECORD_SETS:
        source_csv = SOURCE_V3 / "results" / record_set / PROTOCOL / "ida_raw_all.csv"
        if not source_csv.exists():
            raise FileNotFoundError(source_csv)
        raw = pd.read_csv(source_csv)
        keep = raw["im_value"].round(6).isin([round(x, 6) for x in COARSE_IM_VALUES])
        filtered = raw[keep].copy()
        filtered["im_grid_id"] = "G2coarse_from_G3fine"
        level_map = {float(v): i for i, v in enumerate(COARSE_IM_VALUES)}
        filtered["im_level"] = filtered["im_value"].round(6).map(lambda x: level_map[float(round(x, 1))])

        result_dir = OUT_ROOT / "results" / scenario / record_set / PROTOCOL
        result_dir.mkdir(parents=True, exist_ok=True)
        raw_csv = result_dir / "ida_raw_all.csv"
        filtered.to_csv(raw_csv, index=False)
        run_pipeline(raw_csv, out_dir=result_dir, limits=limits, include_numerical=False)
        result_dirs[record_set] = result_dir
    return result_dirs


def _existing_result_dirs() -> dict[tuple[str, str], Path]:
    result_dirs: dict[tuple[str, str], Path] = {}
    for record_set in RECORD_SETS:
        result_dirs[("v2_N5_G5_existing", record_set)] = (
            SOURCE_V2 / "results" / record_set / PROTOCOL
        )
        result_dirs[("v3_N10_G12_existing", record_set)] = (
            SOURCE_V3 / "results" / record_set / PROTOCOL
        )
    return result_dirs


def _collect_summary(result_dirs: dict[tuple[str, str], Path]) -> pd.DataFrame:
    rows = []
    scenario_meta = {
        "v2_N5_G5_existing": {
            "n_records_per_pool": 5,
            "n_im_levels": 5,
            "record_selection_source": "expanded_pilot_v2_selected",
            "im_grid": "G2_coarse_0p2_to_1p0",
            "open_sees_source": "existing_v2_runs",
        },
        "r34_N5_G12_v2_records": {
            "n_records_per_pool": 5,
            "n_im_levels": 12,
            "record_selection_source": "expanded_pilot_v2_selected",
            "im_grid": "G3_fine_0p1_to_1p2",
            "open_sees_source": "new_r34_runs",
        },
        "r34_N10_G5_v3_records": {
            "n_records_per_pool": 10,
            "n_im_levels": 5,
            "record_selection_source": "sensitivity_v3_selected",
            "im_grid": "G2_coarse_filtered_from_G3",
            "open_sees_source": "existing_v3_level0_filtered",
        },
        "v3_N10_G12_existing": {
            "n_records_per_pool": 10,
            "n_im_levels": 12,
            "record_selection_source": "sensitivity_v3_selected",
            "im_grid": "G3_fine_0p1_to_1p2",
            "open_sees_source": "existing_v3_runs",
        },
    }

    for (scenario, record_set), rd in sorted(result_dirs.items()):
        mle_path = rd / "censored_mle_summary.csv"
        obs_path = rd / "collapse_observations.csv"
        raw_path = rd / "ida_raw_all.csv"
        enriched_path = rd / "ida_raw_all_enriched.csv"
        for p in [mle_path, obs_path, raw_path, enriched_path]:
            if not p.exists():
                raise FileNotFoundError(p)
        mle = pd.read_csv(mle_path)
        obs = pd.read_csv(obs_path)
        raw = pd.read_csv(raw_path)
        enriched = pd.read_csv(enriched_path)
        all_row = mle[mle["group"] == "ALL"].iloc[0].to_dict()
        all_row.update(scenario_meta[scenario])
        all_row["scenario"] = scenario
        all_row["scenario_order"] = SCENARIO_ORDER.index(scenario)
        all_row["record_set"] = record_set
        all_row["protocol"] = PROTOCOL
        all_row["censoring_rate"] = float(obs["censored"].mean())
        all_row["n_runs"] = int(len(raw))
        all_row["n_nonconverged"] = int((~raw["converged"].astype(bool)).sum())
        all_row["n_first_crossing"] = int(enriched["first_crossing"].astype(bool).sum())
        rows.append(all_row)

    summary = pd.DataFrame(rows).sort_values(["scenario_order", "record_set"]).reset_index(drop=True)
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    summary.to_csv(FIG_DIR / "protocol_split_r34_summary.csv", index=False)
    return summary


def _make_ledger(summary: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for scenario, g in summary.groupby("scenario", sort=False):
        ref = g[g["record_set"] == "FF22"].iloc[0]
        theta_ref = float(ref["theta"])
        for _, row in g.sort_values("record_set").iterrows():
            theta = float(row["theta"])
            log_shift = float(np.log(theta / theta_ref)) if theta > 0 and theta_ref > 0 else np.nan
            rows.append(
                {
                    "effect_family": "record_pool_protocol_split_r34",
                    "scenario": scenario,
                    "scenario_order": int(row["scenario_order"]),
                    "reference_record_set": "FF22",
                    "record_set": row["record_set"],
                    "protocol": PROTOCOL,
                    "n_records_per_pool": int(row["n_records_per_pool"]),
                    "n_im_levels": int(row["n_im_levels"]),
                    "record_selection_source": row["record_selection_source"],
                    "im_grid": row["im_grid"],
                    "open_sees_source": row["open_sees_source"],
                    "theta_ref": theta_ref,
                    "theta": theta,
                    "theta_percent_shift_vs_ref": 100.0 * (theta - theta_ref) / theta_ref,
                    "log_theta_shift_vs_ref": log_shift,
                    "psi_binary": abs(log_shift) / 2.0 if np.isfinite(log_shift) else np.nan,
                    "beta": float(row["beta"]) if pd.notna(row["beta"]) else np.nan,
                    "censoring_rate": float(row["censoring_rate"]),
                    "n_runs": int(row["n_runs"]),
                    "n_nonconverged": int(row["n_nonconverged"]),
                }
            )
    ledger = pd.DataFrame(rows).sort_values(["scenario_order", "record_set"]).reset_index(drop=True)
    ledger.to_csv(FIG_DIR / "protocol_split_r34_protocol_effect_ledger.csv", index=False)
    return ledger


def _decompose(ledger: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for contrast in ["FFext", "NF28"]:
        d = ledger[ledger["record_set"] == contrast].set_index("scenario")
        vals = {scenario: float(d.loc[scenario, "log_theta_shift_vs_ref"]) for scenario in SCENARIO_ORDER}
        rows.append(
            {
                "contrast": f"{contrast}_vs_FF22",
                "delta_logtheta_v2_N5_G5": vals["v2_N5_G5_existing"],
                "delta_logtheta_N5_G12_v2_records": vals["r34_N5_G12_v2_records"],
                "delta_logtheta_N10_G5_v3_records": vals["r34_N10_G5_v3_records"],
                "delta_logtheta_v3_N10_G12": vals["v3_N10_G12_existing"],
                "grid_effect_with_v2_records": vals["r34_N5_G12_v2_records"] - vals["v2_N5_G5_existing"],
                "grid_effect_with_v3_records": vals["v3_N10_G12_existing"] - vals["r34_N10_G5_v3_records"],
                "record_subset_count_effect_on_coarse_grid": vals["r34_N10_G5_v3_records"] - vals["v2_N5_G5_existing"],
                "record_subset_count_effect_on_fine_grid": vals["v3_N10_G12_existing"]
                - vals["r34_N5_G12_v2_records"],
                "interpretation": _interpret_contrast(vals),
            }
        )
    out = pd.DataFrame(rows)
    out.to_csv(FIG_DIR / "protocol_split_r34_decomposition.csv", index=False)
    return out


def _interpret_contrast(vals: dict[str, float]) -> str:
    signs = {k: np.sign(v) for k, v in vals.items()}
    if all(v < 0 for v in vals.values()):
        return "negative_in_all_four_cells"
    if all(v > 0 for v in vals.values()):
        return "positive_in_all_four_cells"
    if signs["v2_N5_G5_existing"] != signs["r34_N5_G12_v2_records"] and signs[
        "r34_N10_G5_v3_records"
    ] == signs["v3_N10_G12_existing"]:
        return "grid_sensitive_with_v2_records"
    if signs["v2_N5_G5_existing"] == signs["r34_N5_G12_v2_records"] and signs[
        "r34_N10_G5_v3_records"
    ] != signs["v3_N10_G12_existing"]:
        return "grid_sensitive_with_v3_records"
    if signs["v2_N5_G5_existing"] != signs["r34_N10_G5_v3_records"] and signs[
        "r34_N5_G12_v2_records"
    ] != signs["v3_N10_G12_existing"]:
        return "record_subset_count_sensitive_across_grids"
    return "interaction_sensitive_no_single_factor_explanation"


def _plot(summary: pd.DataFrame, ledger: pd.DataFrame, decomp: pd.DataFrame) -> None:
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    MANUSCRIPT_FIG_DIR.mkdir(parents=True, exist_ok=True)

    scenario_labels = {
        "v2_N5_G5_existing": "N5/G5\nv2",
        "r34_N5_G12_v2_records": "N5/G12\nv2 records",
        "r34_N10_G5_v3_records": "N10/G5\nv3 records",
        "v3_N10_G12_existing": "N10/G12\nv3",
    }
    colors = {"FF22": "#4C78A8", "FFext": "#F58518", "NF28": "#54A24B"}

    fig, ax = plt.subplots(figsize=(8.0, 4.4))
    x = np.arange(len(SCENARIO_ORDER))
    width = 0.24
    for i, record_set in enumerate(RECORD_SETS):
        g = summary[summary["record_set"] == record_set].set_index("scenario").loc[SCENARIO_ORDER]
        ax.bar(x + (i - 1) * width, g["theta"].to_numpy(dtype=float), width=width, color=colors[record_set], label=record_set)
    ax.set_xticks(x, [scenario_labels[s] for s in SCENARIO_ORDER])
    ax.set_ylabel(r"Median capacity $\theta$ (g)")
    ax.set_title("R34 protocol split: record subset/count and IM-grid cells")
    ax.grid(True, axis="y", alpha=0.25)
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "fig_protocol_split_r34_theta.png", dpi=300, bbox_inches="tight")
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(8.0, 4.4))
    for contrast, color in [("FFext", colors["FFext"]), ("NF28", colors["NF28"])]:
        g = ledger[ledger["record_set"] == contrast].set_index("scenario").loc[SCENARIO_ORDER]
        ax.plot(
            x,
            g["log_theta_shift_vs_ref"].to_numpy(dtype=float),
            marker="o",
            linewidth=2.0,
            color=color,
            label=f"{contrast} vs FF22",
        )
    ax.axhline(0.0, color="black", linewidth=1.0)
    ax.set_xticks(x, [scenario_labels[s] for s in SCENARIO_ORDER])
    ax.set_ylabel(r"$\Delta \log \theta$ relative to FF22")
    ax.set_title("R34 protocol split: record-pool contrast attribution")
    ax.grid(True, alpha=0.25)
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "fig_protocol_split_r34_delta_logtheta.png", dpi=300, bbox_inches="tight")
    fig.savefig(MANUSCRIPT_FIG_DIR / "fig13_protocol_split_r34_delta_logtheta.png", dpi=300, bbox_inches="tight")
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(8.0, 4.0))
    y = np.arange(len(decomp))
    parts = [
        ("grid_effect_with_v2_records", "#72B7B2"),
        ("grid_effect_with_v3_records", "#B279A2"),
        ("record_subset_count_effect_on_coarse_grid", "#E45756"),
        ("record_subset_count_effect_on_fine_grid", "#FF9DA6"),
    ]
    offsets = np.linspace(-0.24, 0.24, len(parts))
    for offset, (col, color) in zip(offsets, parts):
        ax.scatter(decomp[col], y + offset, s=45, color=color, label=col)
    ax.axvline(0.0, color="black", linewidth=1.0)
    ax.set_yticks(y, decomp["contrast"])
    ax.set_xlabel(r"Change in contrast $\Delta\log\theta$")
    ax.set_title("R34 protocol split: factor-attribution deltas")
    ax.grid(True, axis="x", alpha=0.25)
    ax.legend(frameon=False, fontsize=8, loc="best")
    fig.tight_layout()
    fig.savefig(FIG_DIR / "fig_protocol_split_r34_factor_deltas.png", dpi=300, bbox_inches="tight")
    plt.close(fig)


def _write_note(summary: pd.DataFrame, ledger: pd.DataFrame, decomp: pd.DataFrame, overlap: pd.DataFrame) -> None:
    lines = [
        "# R34 Protocol Split Summary",
        "",
        "Purpose: split the v2/v3 confounding between record selection/count and IM-grid definition.",
        "",
        "Four cells are evaluated:",
        "",
        "- `v2_N5_G5_existing`: existing Expanded Pilot v2, 5 records per pool and 5 IM levels.",
        "- `r34_N5_G12_v2_records`: new R34 OpenSees runs for the v2-selected records on the 12-level fine grid.",
        "- `r34_N10_G5_v3_records`: existing Sensitivity v3 Level-0 outputs filtered to the 5-level coarse grid.",
        "- `v3_N10_G12_existing`: existing Sensitivity v3, 10 records per pool and 12 IM levels.",
        "",
        "The v2 5-record selection is not a subset of the v3 10-record selection; each pool overlaps by only two records.",
        "Therefore the record factor should be interpreted as a combined record-subset/count effect, not a pure count effect.",
        "",
        "## Selection overlap",
        "",
        "| Record set | v2 n | v3 n | overlap n | overlap gm_ids |",
        "| --- | ---: | ---: | ---: | --- |",
    ]
    for _, row in overlap.iterrows():
        lines.append(
            f"| {row['record_set']} | {int(row['v2_n_records'])} | {int(row['v3_n_records'])} | "
            f"{int(row['overlap_n'])} | {row['overlap_gm_ids']} |"
        )

    lines.extend(
        [
            "",
            "## Record-pool ledger",
            "",
            "| Scenario | Record set | theta | beta | shift vs FF22 (%) | delta logtheta | PSI |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for _, row in ledger.iterrows():
        lines.append(
            f"| {row['scenario']} | {row['record_set']} | {row['theta']:.4f} | {row['beta']:.4f} | "
            f"{row['theta_percent_shift_vs_ref']:+.1f} | {row['log_theta_shift_vs_ref']:+.3f} | "
            f"{row['psi_binary']:.3f} |"
        )

    lines.extend(
        [
            "",
            "## Decomposition",
            "",
            "| Contrast | grid effect, v2 records | grid effect, v3 records | subset/count effect, coarse grid | subset/count effect, fine grid | Interpretation |",
            "| --- | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    for _, row in decomp.iterrows():
        lines.append(
            f"| {row['contrast']} | {row['grid_effect_with_v2_records']:+.3f} | "
            f"{row['grid_effect_with_v3_records']:+.3f} | "
            f"{row['record_subset_count_effect_on_coarse_grid']:+.3f} | "
            f"{row['record_subset_count_effect_on_fine_grid']:+.3f} | {row['interpretation']} |"
        )

    lines.extend(
        [
            "",
            "Gate interpretation:",
            "",
            "- If a contrast changes sign across cells, the manuscript must not present it as a stable record-pool direction.",
            "- If a contrast remains one-sided across all four cells, it can be described as stable across this protocol split, still conditional on the pilot specimen/model family.",
            "- Large grid or subset/count deltas should be reported as active protocol factors rather than folded into a single record-pool claim.",
        ]
    )
    (FIG_DIR / "protocol_split_r34_results_note.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    specimens = pd.read_csv("data/specimen_table_pilot_v1.csv")
    limits = _limits_from_specimens(specimens)
    opensees_exe = Path("tools/opensees_bin/OpenSees3.8.0/bin/OpenSees.exe").resolve()
    if not opensees_exe.exists():
        raise SystemExit(f"OpenSees.exe not found: {opensees_exe}")

    overlap = _write_selection_overlap_note()
    n5_g12_dirs = _run_n5_g12_v2_records(specimens=specimens, limits=limits, opensees_exe=opensees_exe)
    n10_g5_dirs = _filter_n10_g5_from_v3(limits=limits)

    result_dirs = _existing_result_dirs()
    for record_set, rd in n5_g12_dirs.items():
        result_dirs[("r34_N5_G12_v2_records", record_set)] = rd
    for record_set, rd in n10_g5_dirs.items():
        result_dirs[("r34_N10_G5_v3_records", record_set)] = rd

    summary = _collect_summary(result_dirs)
    ledger = _make_ledger(summary)
    decomp = _decompose(ledger)
    _plot(summary, ledger, decomp)
    _write_note(summary, ledger, decomp, overlap)
    print("Wrote R34 protocol split to", OUT_ROOT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
