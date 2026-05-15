from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from paper_c_eesd.postprocess import run_pipeline
from paper_c_eesd.postprocess.collapse_and_mechanism import DemandRatioLimits


SOURCE_ROOT = Path("data/sensitivity_v3/results")
OUT_ROOT = Path("data/threshold_sensitivity_v4")
MANUSCRIPT_FIG_DIR = Path("docs/manuscript_drafts/figures")
RECORD_SETS = ["FF22", "FFext", "NF28"]
PROTOCOL = "P1"
SCENARIOS = {
    "strict_0p8": 0.8,
    "current_1p0": 1.0,
    "relaxed_1p2": 1.2,
}


def _base_limits() -> DemandRatioLimits:
    sp = pd.read_csv("data/specimen_table_pilot_v1.csv").iloc[0]
    return DemandRatioLimits(
        drift_limit=float(sp["drift_limit"]),
        residual_drift_limit=float(sp["residual_drift_limit"]),
        steel_eps_t_limit=float(sp["steel_eps_t_limit"]),
        steel_eps_c_limit=float(sp["steel_eps_c_limit"]),
        concrete_eps_c_limit=float(sp["concrete_eps_c_limit"]),
    )


def _scaled_limits(base: DemandRatioLimits, scale: float) -> DemandRatioLimits:
    return DemandRatioLimits(
        drift_limit=base.drift_limit * scale,
        residual_drift_limit=base.residual_drift_limit * scale,
        steel_eps_t_limit=base.steel_eps_t_limit * scale,
        steel_eps_c_limit=base.steel_eps_c_limit * scale,
        concrete_eps_c_limit=base.concrete_eps_c_limit * scale,
    )


def _run_scenarios() -> dict[tuple[str, str], Path]:
    base = _base_limits()
    result_dirs: dict[tuple[str, str], Path] = {}
    for scenario, scale in SCENARIOS.items():
        limits = _scaled_limits(base, scale)
        for record_set in RECORD_SETS:
            source_csv = SOURCE_ROOT / record_set / PROTOCOL / "ida_raw_all.csv"
            if not source_csv.exists():
                raise FileNotFoundError(source_csv)
            out_dir = OUT_ROOT / "results" / scenario / record_set / PROTOCOL
            run_pipeline(source_csv, out_dir=out_dir, limits=limits, include_numerical=False)
            result_dirs[(scenario, record_set)] = out_dir
    return result_dirs


def _collect_summary(result_dirs: dict[tuple[str, str], Path]) -> pd.DataFrame:
    rows = []
    for (scenario, record_set), rd in sorted(result_dirs.items()):
        mle = pd.read_csv(rd / "censored_mle_summary.csv")
        obs = pd.read_csv(rd / "collapse_observations.csv")
        all_row = mle[mle["group"] == "ALL"].iloc[0].to_dict()
        all_row["scenario"] = scenario
        all_row["threshold_scale"] = SCENARIOS[scenario]
        all_row["record_set"] = record_set
        all_row["protocol"] = PROTOCOL
        all_row["censoring_rate"] = float(obs["censored"].mean())
        rows.append(all_row)
    summary = pd.DataFrame(rows)
    fig_dir = OUT_ROOT / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)
    summary.to_csv(fig_dir / "threshold_sensitivity_v4_summary.csv", index=False)
    return summary


def _make_ledger(summary: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for scenario, g in summary.groupby("scenario", sort=True):
        ref = g[g["record_set"] == "FF22"].iloc[0]
        theta_ref = float(ref["theta"])
        for _, row in g.sort_values("record_set").iterrows():
            theta = float(row["theta"])
            log_shift = float(np.log(theta / theta_ref)) if theta > 0 and theta_ref > 0 else np.nan
            rows.append(
                {
                    "effect_family": "record_pool_threshold_sensitivity",
                    "scenario": scenario,
                    "threshold_scale": float(row["threshold_scale"]),
                    "reference_record_set": "FF22",
                    "record_set": row["record_set"],
                    "protocol": PROTOCOL,
                    "theta_ref": theta_ref,
                    "theta": theta,
                    "theta_percent_shift_vs_ref": 100.0 * (theta - theta_ref) / theta_ref,
                    "log_theta_shift_vs_ref": log_shift,
                    "beta_pool_equiv_binary": abs(log_shift) / 2.0 if np.isfinite(log_shift) else np.nan,
                    "beta": float(row["beta"]) if pd.notna(row["beta"]) else np.nan,
                    "censoring_rate": float(row["censoring_rate"]),
                }
            )
    ledger = pd.DataFrame(rows)
    ledger.to_csv(OUT_ROOT / "figures" / "threshold_sensitivity_v4_protocol_effect_ledger.csv", index=False)
    return ledger


def _plot(summary: pd.DataFrame, ledger: pd.DataFrame) -> None:
    fig_dir = OUT_ROOT / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)
    MANUSCRIPT_FIG_DIR.mkdir(parents=True, exist_ok=True)

    pivot = summary.pivot(index="scenario", columns="record_set", values="theta").loc[list(SCENARIOS)]
    fig, ax = plt.subplots(figsize=(7.5, 4.2))
    x = np.arange(len(pivot.index))
    width = 0.24
    for i, record_set in enumerate(RECORD_SETS):
        ax.bar(x + (i - 1) * width, pivot[record_set], width=width, label=record_set)
    ax.set_xticks(x, [f"{s}\nscale={SCENARIOS[s]:.1f}" for s in pivot.index])
    ax.set_ylabel(r"Median capacity $\theta$ (g)")
    ax.set_title("Threshold sensitivity v4")
    ax.grid(True, axis="y", alpha=0.25)
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(fig_dir / "fig_threshold_sensitivity_v4_theta.png", dpi=300, bbox_inches="tight")
    fig.savefig(MANUSCRIPT_FIG_DIR / "fig9_threshold_sensitivity_v4_theta.png", dpi=300, bbox_inches="tight")
    plt.close(fig)

    led = ledger[ledger["record_set"] != "FF22"].copy()
    fig, ax = plt.subplots(figsize=(7.5, 4.2))
    for record_set, g in led.groupby("record_set"):
        g = g.set_index("scenario").loc[list(SCENARIOS)].reset_index()
        ax.plot(g["threshold_scale"], g["theta_percent_shift_vs_ref"], marker="o", linewidth=1.8, label=record_set)
    ax.axhline(0.0, color="black", linewidth=1.0)
    ax.set_xlabel("Threshold scale")
    ax.set_ylabel("Theta shift relative to FF22 (%)")
    ax.set_title("Record-pool effect across collapse-threshold scales")
    ax.grid(True, alpha=0.25)
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(fig_dir / "fig_threshold_sensitivity_v4_ledger.png", dpi=300, bbox_inches="tight")
    fig.savefig(MANUSCRIPT_FIG_DIR / "fig10_threshold_sensitivity_v4_ledger.png", dpi=300, bbox_inches="tight")
    plt.close(fig)


def _write_note(summary: pd.DataFrame, ledger: pd.DataFrame) -> None:
    lines = [
        "# Threshold Sensitivity v4 Summary",
        "",
        "This analysis reuses Sensitivity v3 Level-0 outputs and reruns only post-processing/MLE.",
        "No additional OpenSees analyses are performed.",
        "",
        "## Scenarios",
        "",
    ]
    for scenario, scale in SCENARIOS.items():
        lines.append(f"- {scenario}: all EDP limits scaled by {scale:.1f}.")
    lines.extend(["", "## Record-pool ledger", ""])
    for _, row in ledger.iterrows():
        lines.append(
            f"- {row['scenario']} | {row['record_set']} vs FF22: "
            f"theta shift={row['theta_percent_shift_vs_ref']:+.1f}%, "
            f"beta_pool={row['beta_pool_equiv_binary']:.3f}."
        )
    (OUT_ROOT / "figures" / "threshold_sensitivity_v4_results_note.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )


def main() -> int:
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    result_dirs = _run_scenarios()
    summary = _collect_summary(result_dirs)
    ledger = _make_ledger(summary)
    _plot(summary, ledger)
    _write_note(summary, ledger)
    print("Wrote threshold sensitivity v4 to", OUT_ROOT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

