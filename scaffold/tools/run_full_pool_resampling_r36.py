from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from paper_c_eesd.ida.run_single_opensees_tcl_ida import (
    SingleTclRunConfig,
    run_single_opensees_tcl_ida,
)
from paper_c_eesd.postprocess import collect_ida_raw_all, run_pipeline, validate_ida_raw_all_df
from paper_c_eesd.postprocess.collapse_and_mechanism import DemandRatioLimits


RECORD_SETS = ["FF22", "FFext", "NF28"]
PROTOCOL = "P1"
IM_VALUES = [round(x, 1) for x in np.arange(0.1, 1.21, 0.1)]
DEFAULT_SEED = 20260514
DEFAULT_B = 10
DEFAULT_RECORDS_PER_POOL = 10
OUT_ROOT = Path("data/full_pool_resampling_r36")
RUN_ROOT = Path("data/r36_full_pool_runs")
ROUND_ROOT = Path(
    "rounds/R36_full_pool_resampling_r1_2026_05_14"
)
MANUSCRIPT_FIG_DIR = Path("docs/manuscript_drafts/figures")


@dataclass(frozen=True, slots=True)
class FitRow:
    subset_id: int
    record_set: str
    theta: float
    beta: float
    mu: float
    n_total: int
    n_observed: int
    n_censored: int
    log_likelihood: float
    censoring_rate: float
    n_runs: int
    n_nonconverged: int
    n_first_crossing: int
    fit_converged: bool


def _safe_name(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", str(s))[:80]


def _select_by_pga_span(df: pd.DataFrame, n: int) -> pd.DataFrame:
    d = df.dropna(subset=["pga_g"]).sort_values("pga_g", ascending=False).reset_index(drop=True)
    if len(d) <= n:
        return d.copy()
    idx = np.linspace(0, len(d) - 1, n).round().astype(int)
    return d.iloc[idx].copy()


def _eligible_at2(manifest: pd.DataFrame, gm_set: str, record_set: str) -> pd.DataFrame:
    d = manifest[(manifest["gm_set"] == gm_set) & manifest["path"].astype(str).str.endswith(".AT2")].copy()
    d = d[~d["gm_id"].astype(str).str.contains("UP|--V", regex=True, case=False, na=False)]
    d = d.dropna(subset=["pga_g"]).sort_values(["gm_id", "pga_g"], ascending=[True, False])
    d = d.drop_duplicates(subset=["gm_id"], keep="first").reset_index(drop=True)
    d["record_set"] = record_set
    d["base_eq_id"] = ""
    d["eligibility_rule"] = f"{gm_set}: AT2 horizontal components, vertical/UP excluded, duplicate gm_id removed"
    return d[["record_set", "gm_id", "base_eq_id", "pga_g", "path", "eligibility_rule"]].copy()


def _eligible_nf28(nf_manifest: pd.DataFrame) -> pd.DataFrame:
    d = nf_manifest[nf_manifest["ready_for_time_history"].astype(bool)].copy()
    d = d.dropna(subset=["base_eq_id", "pga_g"])
    d = d.sort_values("pga_g", ascending=False).drop_duplicates(subset=["base_eq_id"], keep="first")
    d = d.reset_index(drop=True)
    d["record_set"] = "NF28"
    d["eligibility_rule"] = "ready near-field horizontal components; one strongest component per base_eq_id"
    return d[["record_set", "gm_id", "base_eq_id", "pga_g", "path", "eligibility_rule"]].copy()


def _load_eligible_pools() -> dict[str, pd.DataFrame]:
    manifest = pd.read_csv("data/ground_motions/_derived/gm_manifest.csv")
    nf_manifest = pd.read_csv("data/ground_motions/_derived/nf28_sorted_manifest.csv")
    pools = {
        "FF22": _eligible_at2(manifest, "P695_FF22_AT2_original", "FF22"),
        "FFext": _eligible_at2(manifest, "FFext_AT2_flat", "FFext"),
        "NF28": _eligible_nf28(nf_manifest),
    }
    return pools


def _write_eligible_pools(pools: dict[str, pd.DataFrame]) -> pd.DataFrame:
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    rows = []
    for record_set, df in pools.items():
        df.to_csv(OUT_ROOT / f"eligible_{record_set}.csv", index=False)
        rows.append(
            {
                "record_set": record_set,
                "n_eligible_records": int(len(df)),
                "min_pga_g": float(df["pga_g"].min()),
                "max_pga_g": float(df["pga_g"].max()),
                "eligibility_rule": str(df["eligibility_rule"].iloc[0]),
            }
        )
    summary = pd.DataFrame(rows)
    summary.to_csv(OUT_ROOT / "r36_eligible_pool_summary.csv", index=False)
    return summary


def _build_subset_manifest(
    pools: dict[str, pd.DataFrame],
    *,
    b: int,
    records_per_pool: int,
    seed: int,
) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows: list[dict[str, object]] = []
    for subset_id in range(b):
        for record_set in RECORD_SETS:
            pool = pools[record_set].reset_index(drop=True)
            if len(pool) < records_per_pool:
                raise ValueError(
                    f"{record_set} has only {len(pool)} eligible records; cannot draw {records_per_pool}."
                )
            draw_idx = rng.choice(pool.index.to_numpy(), size=records_per_pool, replace=False)
            draw = pool.loc[draw_idx].reset_index(drop=True)
            for draw_order, row in draw.iterrows():
                rows.append(
                    {
                        "subset_id": int(subset_id),
                        "record_set": record_set,
                        "draw_order": int(draw_order),
                        "gm_id": str(row["gm_id"]),
                        "base_eq_id": str(row.get("base_eq_id", "")),
                        "pga_g": float(row["pga_g"]),
                        "path": str(row["path"]),
                        "seed": int(seed),
                        "records_per_pool": int(records_per_pool),
                        "sampling": "without_replacement_within_subset",
                    }
                )
    manifest = pd.DataFrame(rows)
    manifest.to_csv(OUT_ROOT / "r36_full_pool_subset_manifest.csv", index=False)
    return manifest


def _write_data_leakage_check(manifest: pd.DataFrame, pools: dict[str, pd.DataFrame]) -> dict[str, object]:
    checks: list[dict[str, object]] = []
    for (subset_id, record_set), g in manifest.groupby(["subset_id", "record_set"], sort=True):
        duplicate_gm = int(g["gm_id"].duplicated().sum())
        checks.append(
            {
                "check": "duplicate_gm_within_subset_pool",
                "subset_id": int(subset_id),
                "record_set": record_set,
                "n_duplicate": duplicate_gm,
                "status": "PASS" if duplicate_gm == 0 else "FAIL",
            }
        )
    for record_set, pool in pools.items():
        checks.append(
            {
                "check": "eligible_pool_has_enough_records",
                "subset_id": "",
                "record_set": record_set,
                "n_duplicate": "",
                "status": "PASS" if len(pool) >= DEFAULT_RECORDS_PER_POOL else "FAIL",
                "n_eligible": int(len(pool)),
            }
        )
    check_df = pd.DataFrame(checks)
    check_df.to_csv(OUT_ROOT / "r36_data_leakage_checks.csv", index=False)
    n_fail = int((check_df["status"] == "FAIL").sum())
    lines = [
        "# R36 Data-Leakage and Sampling Check",
        "",
        "This engineering workflow has no train/test split. The relevant leakage checks are",
        "record-identity duplication inside each sampled subset, missing/duplicate eligible",
        "records, and accidental reuse of vertical components.",
        "",
        f"- Checked subset-pool duplicate `gm_id`: failures = {n_fail}.",
        "- Sampling is without replacement within each subset and record pool.",
        "- FF22/FFext AT2 pools remove `UP` and `--V` labels and duplicate `gm_id` rows.",
        "- NF28 uses one strongest horizontal component per `base_eq_id`.",
        "",
        "Detailed machine-readable checks: `data/full_pool_resampling_r36/r36_data_leakage_checks.csv`.",
    ]
    status = "PASS" if n_fail == 0 else "FAIL"
    (ROUND_ROOT / "outputs/round1").mkdir(parents=True, exist_ok=True)
    (ROUND_ROOT / "outputs/round1/data_leakage_check.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )
    return {"status": status, "n_fail": n_fail}


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


def _run_bank(
    manifest: pd.DataFrame,
    specimens: pd.DataFrame,
    *,
    opensees_exe: Path,
    max_new_runs: int | None,
    dry_run: bool,
    use_completion_cache: bool,
) -> dict[str, object]:
    selected = (
        manifest[["record_set", "gm_id", "path"]]
        .drop_duplicates()
        .sort_values(["record_set", "gm_id"])
        .reset_index(drop=True)
    )
    expected_unique_runs = int(len(selected) * len(specimens) * len(IM_VALUES))
    cache_path = OUT_ROOT / "r36_run_completion_cache.csv"
    complete_cache: set[str] = set()
    if use_completion_cache and cache_path.exists():
        cache_df = pd.read_csv(cache_path)
        if "run_dir" in cache_df.columns:
            complete_cache = set(cache_df["run_dir"].astype(str))
    n_new = 0
    n_skipped = 0
    n_blocked = 0
    for _, gm in selected.iterrows():
        record_set = str(gm["record_set"])
        gm_id = str(gm["gm_id"])
        gm_path = Path(str(gm["path"]))
        for _, sp in specimens.iterrows():
            specimen_id = str(sp["specimen_id"])
            for im_level, im_value in enumerate(IM_VALUES):
                run_dir = RUN_ROOT / record_set / _safe_name(gm_id) / specimen_id / f"{im_level:02d}"
                run_key = run_dir.as_posix()
                if use_completion_cache and run_key in complete_cache:
                    n_skipped += 1
                    continue
                if _run_is_complete(run_dir):
                    n_skipped += 1
                    if use_completion_cache:
                        complete_cache.add(run_key)
                    continue
                if dry_run or (max_new_runs is not None and n_new >= max_new_runs):
                    n_blocked += 1
                    continue
                cfg = SingleTclRunConfig(
                    specimen_id=specimen_id,
                    gm_id=gm_id,
                    analysis_protocol_id=PROTOCOL,
                    im_grid_id="G3fine_r36",
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
                n_new += 1
                if use_completion_cache and _run_is_complete(run_dir):
                    complete_cache.add(run_key)
    if use_completion_cache:
        pd.DataFrame({"run_dir": sorted(complete_cache)}).to_csv(cache_path, index=False)
    summary = {
        "expected_unique_run_bank_runs": expected_unique_runs,
        "new_runs": n_new,
        "skipped_complete_runs": n_skipped,
        "blocked_not_run": n_blocked,
        "dry_run": bool(dry_run),
        "max_new_runs": max_new_runs if max_new_runs is not None else "",
        "use_completion_cache": bool(use_completion_cache),
    }
    (OUT_ROOT / "r36_run_bank_execution_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    print("R36 run bank:", json.dumps(summary, indent=2))
    return summary


def _collect_bank_raw() -> pd.DataFrame:
    frames = []
    for record_set in RECORD_SETS:
        root = RUN_ROOT / record_set
        df = collect_ida_raw_all(root)
        validate_ida_raw_all_df(df)
        df["record_set"] = record_set
        frames.append(df)
    raw = pd.concat(frames, ignore_index=True)
    raw.to_csv(OUT_ROOT / "r36_ida_raw_all.csv", index=False)
    return raw


def _fit_subset(
    *,
    subset_id: int,
    record_set: str,
    raw_subset: pd.DataFrame,
    limits: DemandRatioLimits,
) -> tuple[FitRow, pd.DataFrame]:
    result_dir = OUT_ROOT / "results" / f"subset_{subset_id:04d}" / record_set / PROTOCOL
    result_dir.mkdir(parents=True, exist_ok=True)
    raw_csv = result_dir / "ida_raw_all.csv"
    raw_subset = raw_subset.drop(columns=["record_set"], errors="ignore").copy()
    raw_subset.to_csv(raw_csv, index=False)
    run_pipeline(raw_csv, out_dir=result_dir, limits=limits, include_numerical=False)
    mle = pd.read_csv(result_dir / "censored_mle_summary.csv")
    obs = pd.read_csv(result_dir / "collapse_observations.csv")
    enriched = pd.read_csv(result_dir / "ida_raw_all_enriched.csv")
    all_row = mle[mle["group"] == "ALL"].iloc[0]
    theta = float(all_row["theta"]) if pd.notna(all_row["theta"]) else math.nan
    beta = float(all_row["beta"]) if pd.notna(all_row["beta"]) else math.nan
    mu = float(all_row["mu"]) if pd.notna(all_row["mu"]) else math.nan
    fit = FitRow(
        subset_id=int(subset_id),
        record_set=record_set,
        theta=theta,
        beta=beta,
        mu=mu,
        n_total=int(all_row["n_total"]),
        n_observed=int(all_row["n_observed"]),
        n_censored=int(all_row["n_censored"]),
        log_likelihood=float(all_row["log_likelihood"]) if pd.notna(all_row["log_likelihood"]) else math.nan,
        censoring_rate=float(obs["censored"].mean()),
        n_runs=int(len(raw_subset)),
        n_nonconverged=int((~raw_subset["converged"].astype(bool)).sum()),
        n_first_crossing=int(enriched["first_crossing"].astype(bool).sum()),
        fit_converged=bool(pd.notna(theta) and pd.notna(beta)),
    )
    obs["subset_id"] = int(subset_id)
    obs["record_set"] = record_set
    return fit, obs


def _fit_all_subsets(
    manifest: pd.DataFrame,
    raw_bank: pd.DataFrame,
    limits: DemandRatioLimits,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    fit_rows: list[FitRow] = []
    obs_rows: list[pd.DataFrame] = []
    for subset_id in sorted(manifest["subset_id"].unique()):
        for record_set in RECORD_SETS:
            gm_ids = manifest[
                (manifest["subset_id"] == subset_id) & (manifest["record_set"] == record_set)
            ]["gm_id"].astype(str)
            raw_subset = raw_bank[
                (raw_bank["record_set"] == record_set) & (raw_bank["gm_id"].astype(str).isin(set(gm_ids)))
            ].copy()
            fit, obs = _fit_subset(
                subset_id=int(subset_id),
                record_set=record_set,
                raw_subset=raw_subset,
                limits=limits,
            )
            fit_rows.append(fit)
            obs_rows.append(obs)
    fits = pd.DataFrame([asdict(r) for r in fit_rows])
    obs_all = pd.concat(obs_rows, ignore_index=True)
    fits.to_csv(OUT_ROOT / "r36_censored_mle_by_subset.csv", index=False)
    obs_all.to_csv(OUT_ROOT / "r36_collapse_observations.csv", index=False)
    return fits, obs_all


def _make_effect_distribution(fits: pd.DataFrame) -> pd.DataFrame:
    valid = fits[fits["fit_converged"].astype(bool)].copy()
    wide_theta = valid.pivot(index="subset_id", columns="record_set", values="theta")
    wide_beta = valid.pivot(index="subset_id", columns="record_set", values="beta")
    rows = []
    for contrast in ["FFext", "NF28"]:
        available = wide_theta[["FF22", contrast]].dropna()
        delta = np.log(available[contrast] / available["FF22"])
        rows.append(
            pd.DataFrame(
                {
                    "subset_id": available.index.to_numpy(dtype=int),
                    "contrast": f"{contrast}_vs_FF22",
                    "theta_ref": available["FF22"].to_numpy(dtype=float),
                    "theta_contrast": available[contrast].to_numpy(dtype=float),
                    "beta_ref": wide_beta.loc[available.index, "FF22"].to_numpy(dtype=float),
                    "beta_contrast": wide_beta.loc[available.index, contrast].to_numpy(dtype=float),
                    "delta_logtheta": delta.to_numpy(dtype=float),
                    "theta_percent_shift": (np.exp(delta.to_numpy(dtype=float)) - 1.0) * 100.0,
                    "psi": np.abs(delta.to_numpy(dtype=float)) / 2.0,
                }
            )
        )
    effects = pd.concat(rows, ignore_index=True)
    effects.to_csv(OUT_ROOT / "r36_protocol_effect_distribution.csv", index=False)
    return effects


def _holm_adjust(pvals: list[float]) -> list[float]:
    order = np.argsort(pvals)
    adjusted = np.empty(len(pvals), dtype=float)
    prev = 0.0
    m = len(pvals)
    for rank, idx in enumerate(order):
        adj = min(1.0, (m - rank) * pvals[idx])
        prev = max(prev, adj)
        adjusted[idx] = prev
    return adjusted.tolist()


def _format_md_value(value: object) -> str:
    if pd.isna(value):
        return ""
    if isinstance(value, float):
        return f"{value:.6g}"
    return str(value).replace("|", "\\|").replace("\n", " ")


def _df_to_markdown(df: pd.DataFrame) -> str:
    if df is None or df.empty:
        return "_No rows._"
    cols = list(df.columns)
    lines = [
        "| " + " | ".join(cols) + " |",
        "| " + " | ".join(["---"] * len(cols)) + " |",
    ]
    for _, row in df.iterrows():
        lines.append("| " + " | ".join(_format_md_value(row[c]) for c in cols) + " |")
    return "\n".join(lines)


def _summarize_effects(effects: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    summary_rows = []
    test_rows = []
    raw_pvals = []
    contrasts = []
    for contrast, g in effects.groupby("contrast", sort=True):
        delta = g["delta_logtheta"].to_numpy(dtype=float)
        n = int(delta.size)
        k_neg = int(np.sum(delta < 0.0))
        mean = float(np.mean(delta))
        std = float(np.std(delta, ddof=1)) if n > 1 else math.nan
        se = float(std / math.sqrt(n)) if n > 1 else math.nan
        ci95_t = stats.t.interval(0.95, df=n - 1, loc=mean, scale=se) if n > 1 else (math.nan, math.nan)
        q05, q50, q95 = np.quantile(delta, [0.05, 0.5, 0.95])
        try:
            wilcoxon_p = float(stats.wilcoxon(delta, alternative="two-sided").pvalue)
        except ValueError:
            wilcoxon_p = math.nan
        sign_p = float(stats.binomtest(k_neg, n, p=0.5, alternative="two-sided").pvalue)
        raw_pvals.append(sign_p)
        contrasts.append(contrast)
        summary_rows.append(
            {
                "contrast": contrast,
                "B": n,
                "mean_delta_logtheta": mean,
                "std_delta_logtheta": std,
                "ci95_t_low_delta_logtheta": float(ci95_t[0]),
                "ci95_t_high_delta_logtheta": float(ci95_t[1]),
                "q05_delta_logtheta": float(q05),
                "median_delta_logtheta": float(q50),
                "q95_delta_logtheta": float(q95),
                "p_delta_logtheta_lt_0": float(k_neg / n),
                "median_theta_percent_shift": float((math.exp(float(q50)) - 1.0) * 100.0),
                "q05_theta_percent_shift": float((math.exp(float(q05)) - 1.0) * 100.0),
                "q95_theta_percent_shift": float((math.exp(float(q95)) - 1.0) * 100.0),
                "median_psi": float(np.median(np.abs(delta) / 2.0)),
                "gate_interpretation": _interpret_delta(delta),
            }
        )
        test_rows.append(
            {
                "contrast": contrast,
                "test": "sign_test_delta_logtheta_vs_zero",
                "n": n,
                "k_negative": k_neg,
                "raw_p_value": sign_p,
                "holm_p_value": math.nan,
                "effect_size_p_negative": float(k_neg / n),
                "note": "Monte Carlo subset-draw sign test; interpret as stability screen, not universal inference.",
            }
        )
        test_rows.append(
            {
                "contrast": contrast,
                "test": "wilcoxon_signed_rank_delta_logtheta_vs_zero",
                "n": n,
                "k_negative": k_neg,
                "raw_p_value": wilcoxon_p,
                "holm_p_value": math.nan,
                "effect_size_p_negative": float(k_neg / n),
                "note": "Uses subset-level delta values; small-B result is diagnostic.",
            }
        )
    holm = _holm_adjust(raw_pvals)
    for row in test_rows:
        if row["test"] == "sign_test_delta_logtheta_vs_zero":
            row["holm_p_value"] = holm[contrasts.index(row["contrast"])]
    summary = pd.DataFrame(summary_rows)
    tests = pd.DataFrame(test_rows)
    summary.to_csv(OUT_ROOT / "r36_summary_table.csv", index=False)
    tests.to_csv(OUT_ROOT / "r36_statistical_tests.csv", index=False)
    round_out = ROUND_ROOT / "outputs/round1"
    round_out.mkdir(parents=True, exist_ok=True)
    summary.to_csv(round_out / "main_results.csv", index=False)
    tests.to_csv(round_out / "statistical_tests.csv", index=False)
    return summary, tests


def _interpret_delta(delta: np.ndarray) -> str:
    if delta.size == 0:
        return "no_converged_draws"
    q05, q95 = np.quantile(delta, [0.05, 0.95])
    p_neg = float(np.mean(delta < 0.0))
    if q95 < 0.0 and p_neg >= 0.95:
        return "strong_direction_stable_negative"
    if q95 < 0.0 and p_neg >= 0.90:
        return "direction_stable_negative_at_90pct_gate"
    if q05 > 0.0 and p_neg <= 0.05:
        return "strong_direction_stable_positive"
    if q05 > 0.0 and p_neg <= 0.10:
        return "direction_stable_positive_at_90pct_gate"
    return "sign_or_magnitude_sensitive_under_full_pool_resampling"


def _plot_outputs(fits: pd.DataFrame, effects: pd.DataFrame, summary: pd.DataFrame) -> None:
    fig_dir = OUT_ROOT / "figures"
    round_out = ROUND_ROOT / "outputs/round1"
    for p in [fig_dir, round_out, MANUSCRIPT_FIG_DIR]:
        p.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    for contrast, color in [("FFext_vs_FF22", "#F58518"), ("NF28_vs_FF22", "#54A24B")]:
        x = effects[effects["contrast"] == contrast]["delta_logtheta"].to_numpy(dtype=float)
        ax.hist(x, bins=min(12, max(4, len(x))), alpha=0.55, density=False, label=contrast, color=color)
    ax.axvline(0.0, color="black", linewidth=1.0)
    ax.set_xlabel(r"$\Delta \log \theta$ relative to FF22")
    ax.set_ylabel("Subset count")
    ax.set_title("R36 full-pool subset resampling: record-pool contrasts")
    ax.grid(True, alpha=0.25)
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(fig_dir / "fig14_full_pool_resampling_delta_logtheta.png", dpi=300, bbox_inches="tight")
    fig.savefig(round_out / "confidence_intervals.png", dpi=300, bbox_inches="tight")
    fig.savefig(MANUSCRIPT_FIG_DIR / "fig14_full_pool_resampling_delta_logtheta.png", dpi=300, bbox_inches="tight")
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    for contrast, color in [("FFext_vs_FF22", "#F58518"), ("NF28_vs_FF22", "#54A24B")]:
        g = effects[effects["contrast"] == contrast].sort_values("subset_id")
        vals = g["delta_logtheta"].to_numpy(dtype=float)
        cum_median = [float(np.median(vals[: i + 1])) for i in range(len(vals))]
        ax.plot(g["subset_id"], cum_median, marker="o", label=contrast, color=color)
    ax.axhline(0.0, color="black", linewidth=1.0)
    ax.set_xlabel("Subset draw")
    ax.set_ylabel(r"Cumulative median $\Delta \log \theta$")
    ax.set_title("R36 fail-fast stability trace")
    ax.grid(True, alpha=0.25)
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(fig_dir / "fig_r36_seed_stability.png", dpi=300, bbox_inches="tight")
    fig.savefig(round_out / "seed_stability.png", dpi=300, bbox_inches="tight")
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    for record_set, color in zip(RECORD_SETS, ["#4C78A8", "#F58518", "#54A24B"]):
        x = fits[fits["record_set"] == record_set]["theta"].to_numpy(dtype=float)
        ax.scatter(
            fits[fits["record_set"] == record_set]["subset_id"],
            x,
            label=record_set,
            color=color,
            alpha=0.8,
        )
    ax.set_xlabel("Subset draw")
    ax.set_ylabel(r"Fitted median capacity $\theta$ (g)")
    ax.set_title("R36 subset-level fitted capacities")
    ax.grid(True, alpha=0.25)
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(fig_dir / "fig_r36_theta_by_subset.png", dpi=300, bbox_inches="tight")
    plt.close(fig)


def _write_reports(
    *,
    args: argparse.Namespace,
    start_time: float,
    eligible_summary: pd.DataFrame,
    manifest: pd.DataFrame,
    fits: pd.DataFrame | None,
    effects: pd.DataFrame | None,
    summary: pd.DataFrame | None,
    tests: pd.DataFrame | None,
    leakage: dict[str, object],
) -> None:
    round_out = ROUND_ROOT / "outputs/round1"
    round_docs = ROUND_ROOT / "docs"
    round_out.mkdir(parents=True, exist_ok=True)
    round_docs.mkdir(parents=True, exist_ok=True)
    elapsed = time.time() - start_time
    execution = json.loads((OUT_ROOT / "r36_run_bank_execution_summary.json").read_text(encoding="utf-8"))
    fit_rate = math.nan
    if fits is not None and len(fits):
        fit_rate = float(fits["fit_converged"].mean())
    lines = [
        "# R36 Round-1 Reproducibility Report",
        "",
        f"Command: `python tools/run_full_pool_resampling_r36.py --b {args.b} --records-per-pool {args.records_per_pool} --seed {args.seed}`",
        f"Dry run: `{bool(args.dry_run)}`",
        f"Elapsed seconds: {elapsed:.1f}",
        "",
        "## Inputs",
        "",
        "- `data/ground_motions/_derived/gm_manifest.csv`",
        "- `data/ground_motions/_derived/nf28_sorted_manifest.csv`",
        "- `data/specimen_table_pilot_v1.csv`",
        f"- OpenSees executable: `{Path(args.opensees_exe).resolve()}`",
        "",
        "## Sampling",
        "",
        _df_to_markdown(eligible_summary),
        "",
        f"- B = {args.b}",
        f"- Records per pool = {args.records_per_pool}",
        f"- Seed = {args.seed}",
        "- Sampling = without replacement within each subset and pool.",
        "",
        "## Execution Summary",
        "",
        f"- Expected unique run-bank runs: {execution['expected_unique_run_bank_runs']}",
        f"- New OpenSees runs: {execution['new_runs']}",
        f"- Skipped complete runs: {execution['skipped_complete_runs']}",
        f"- Blocked/not run: {execution['blocked_not_run']}",
        f"- Data leakage check: {leakage['status']} ({leakage['n_fail']} failures)",
        f"- MLE fit convergence rate: {fit_rate:.3f}" if not math.isnan(fit_rate) else "- MLE fit convergence rate: not evaluated",
        "",
        "## Output Files",
        "",
        "- `data/full_pool_resampling_r36/r36_full_pool_subset_manifest.csv`",
        "- `data/full_pool_resampling_r36/r36_ida_raw_all.csv`",
        "- `data/full_pool_resampling_r36/r36_collapse_observations.csv`",
        "- `data/full_pool_resampling_r36/r36_censored_mle_by_subset.csv`",
        "- `data/full_pool_resampling_r36/r36_protocol_effect_distribution.csv`",
        "- `data/full_pool_resampling_r36/r36_summary_table.csv`",
        "- `data/full_pool_resampling_r36/r36_statistical_tests.csv`",
    ]
    (round_out / "reproducibility_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    metric = [
        "# R36 Metric Justification",
        "",
        "This is an engineering fragility/protocol-sensitivity study, not a supervised ML task.",
        "Therefore classification metrics such as accuracy/F1 are not meaningful. The relevant",
        "metrics are fitted median capacity theta, log-median shift relative to FF22, dispersion",
        "beta, right-censoring rate, non-convergence count, subset-draw interval, and sign probability.",
        "",
        "- Primary effect size: `delta_logtheta = log(theta_contrast / theta_FF22)`.",
        "- Reporting convenience: `PSI = |delta_logtheta| / 2`, study-specific only.",
        "- Stability criterion: 5-95% subset interval and `P(delta_logtheta < 0)`.",
        "- Statistical screen: sign test with Holm adjustment across two contrasts, plus Wilcoxon diagnostic.",
    ]
    (round_out / "metric_justification.md").write_text("\n".join(metric) + "\n", encoding="utf-8")

    if summary is None:
        return
    claim = [
        "# CLAIM_MATRIX Round 1",
        "",
        "| Claim ID | Claim | R36 evidence | Grade after R36 | Text action |",
        "| --- | --- | --- | --- | --- |",
    ]
    for _, row in summary.iterrows():
        claim.append(
            f"| R36-{row['contrast']} | Record-pool contrast distribution from full eligible pool sampling | "
            f"B={int(row['B'])}, median delta={row['median_delta_logtheta']:.3f}, "
            f"5-95%=[{row['q05_delta_logtheta']:.3f}, {row['q95_delta_logtheta']:.3f}], "
            f"P(delta<0)={row['p_delta_logtheta_lt_0']:.3f} | "
            f"{'B' if 'direction_stable' in row['gate_interpretation'] else 'C'} | "
            f"{row['gate_interpretation']} |"
        )
    (round_docs / "CLAIM_MATRIX_round1.md").write_text("\n".join(claim) + "\n", encoding="utf-8")

    gate_status = "PASS"
    blocked = int(execution["blocked_not_run"])
    if leakage["status"] != "PASS" or blocked > 0 or (not math.isnan(fit_rate) and fit_rate < 0.95):
        gate_status = "FIX"
    gate = [
        "# GATE_REPORT Round 1",
        "",
        f"GATE status: `{gate_status}`",
        "",
        "## Results",
        "",
        _df_to_markdown(summary),
        "",
        "## Statistical Tests",
        "",
        _df_to_markdown(tests) if tests is not None else "Not evaluated.",
        "",
        "## Gate Criteria",
        "",
        f"- Data leakage/sampling check: {leakage['status']}.",
        f"- Blocked/not run count: {blocked}.",
        f"- MLE fit convergence rate: {fit_rate:.3f}" if not math.isnan(fit_rate) else "- MLE fit convergence rate: not evaluated.",
        "",
        "## Decision Rule",
        "",
        "- PASS means manuscript may use R36 B=10 as a fail-fast diagnostic, but B=30 is still recommended before high-confidence submission language.",
        "- FIX means repair run completion, sampling, or fit convergence before scaling.",
        "- FAIL would mean the central record-pool claim is contradicted; no FAIL condition is assigned automatically by this script.",
    ]
    (round_docs / "GATE_REPORT_round1.md").write_text("\n".join(gate) + "\n", encoding="utf-8")


def _parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--b", type=int, default=DEFAULT_B)
    ap.add_argument("--records-per-pool", type=int, default=DEFAULT_RECORDS_PER_POOL)
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED)
    ap.add_argument(
        "--opensees-exe",
        type=Path,
        default=Path("tools/opensees_bin/OpenSees3.8.0/bin/OpenSees.exe"),
    )
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--max-new-runs", type=int, default=None)
    ap.add_argument(
        "--run-bank-only",
        action="store_true",
        help="Run or resume OpenSees run bank, write reproducibility status, then stop before subset fits.",
    )
    ap.add_argument(
        "--use-completion-cache",
        action="store_true",
        help=(
            "Use data/full_pool_resampling_r36/r36_run_completion_cache.csv to avoid "
            "rechecking already completed run directories. Disabled by default."
        ),
    )
    return ap.parse_args(list(argv) if argv is not None else None)


def _append_run_bank_history(args: argparse.Namespace, execution: dict, start_time: float) -> None:
    """Append-only runtime audit; does not affect any scientific output."""
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    path = OUT_ROOT / "r36_run_bank_execution_history.csv"
    row = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "elapsed_seconds": f"{time.time() - start_time:.3f}",
        "b": int(args.b),
        "records_per_pool": int(args.records_per_pool),
        "seed": int(args.seed),
        "max_new_runs": "" if args.max_new_runs is None else int(args.max_new_runs),
        "run_bank_only": bool(args.run_bank_only),
        "dry_run": bool(args.dry_run),
        "use_completion_cache": bool(args.use_completion_cache),
        "expected_unique_run_bank_runs": execution.get("expected_unique_run_bank_runs", ""),
        "new_runs": execution.get("new_runs", ""),
        "skipped_complete_runs": execution.get("skipped_complete_runs", ""),
        "blocked_not_run": execution.get("blocked_not_run", ""),
    }
    fieldnames = list(row.keys())
    exists = path.exists()
    if exists:
        with path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            existing_rows = list(reader)
            existing_fields = reader.fieldnames or []
        if existing_fields != fieldnames:
            normalized = []
            for old in existing_rows:
                fixed = {k: old.get(k, "") for k in fieldnames}
                overflow = old.get(None) or []
                if old.get("expected_unique_run_bank_runs") in {"True", "False"}:
                    fixed["use_completion_cache"] = old.get("expected_unique_run_bank_runs", "")
                    fixed["expected_unique_run_bank_runs"] = old.get("new_runs", "")
                    fixed["new_runs"] = old.get("skipped_complete_runs", "")
                    fixed["skipped_complete_runs"] = old.get("blocked_not_run", "")
                    fixed["blocked_not_run"] = overflow[0] if overflow else ""
                normalized.append(fixed)
            with path.open("w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(normalized)
    with path.open("a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not exists:
            writer.writeheader()
        writer.writerow(row)


def main(argv: Iterable[str] | None = None) -> int:
    start = time.time()
    args = _parse_args(argv)
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    ROUND_ROOT.mkdir(parents=True, exist_ok=True)
    opensees_exe = Path(args.opensees_exe).resolve()
    if not opensees_exe.exists():
        raise SystemExit(f"OpenSees.exe not found: {opensees_exe}")

    pools = _load_eligible_pools()
    eligible_summary = _write_eligible_pools(pools)
    manifest = _build_subset_manifest(
        pools,
        b=int(args.b),
        records_per_pool=int(args.records_per_pool),
        seed=int(args.seed),
    )
    leakage = _write_data_leakage_check(manifest, pools)
    specimens = pd.read_csv("data/specimen_table_pilot_v1.csv")
    execution = _run_bank(
        manifest,
        specimens,
        opensees_exe=opensees_exe,
        max_new_runs=args.max_new_runs,
        dry_run=bool(args.dry_run),
        use_completion_cache=bool(args.use_completion_cache),
    )
    _append_run_bank_history(args, execution, start)
    if args.dry_run or args.run_bank_only or int(execution["blocked_not_run"]) > 0:
        _write_reports(
            args=args,
            start_time=start,
            eligible_summary=eligible_summary,
            manifest=manifest,
            fits=None,
            effects=None,
            summary=None,
            tests=None,
            leakage=leakage,
        )
        if args.dry_run:
            print("Dry run complete. Manifest and eligibility checks written.")
        elif args.run_bank_only:
            print("Run-bank-only step complete. Re-run until blocked_not_run is 0, then run without --run-bank-only.")
        else:
            print("Run bank incomplete; stopping before subset fits.")
        return 0

    raw_bank = _collect_bank_raw()
    limits = _limits_from_specimens(specimens)
    fits, _obs = _fit_all_subsets(manifest, raw_bank, limits)
    effects = _make_effect_distribution(fits)
    summary, tests = _summarize_effects(effects)
    _plot_outputs(fits, effects, summary)
    _write_reports(
        args=args,
        start_time=start,
        eligible_summary=eligible_summary,
        manifest=manifest,
        fits=fits,
        effects=effects,
        summary=summary,
        tests=tests,
        leakage=leakage,
    )
    print(summary.to_string(index=False))
    print(tests.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
