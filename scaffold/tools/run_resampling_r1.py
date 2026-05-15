from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from paper_c_eesd.fragility.fit_fragility import fit_lognormal_capacity_censored_mle


SOURCE_ROOT = Path("data/sensitivity_v3/results")
OUT_ROOT = Path("data/resampling_r1")
FIG_DIR = OUT_ROOT / "figures"
MANUSCRIPT_FIG_DIR = Path("docs/manuscript_drafts/figures")
RECORD_SETS = ["FF22", "FFext", "NF28"]
PROTOCOL = "P1"
DEFAULT_B = 1000
DEFAULT_RECORDS_PER_POOL = 10
DEFAULT_SEED = 20260513


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


def _load_observations() -> dict[str, pd.DataFrame]:
    data: dict[str, pd.DataFrame] = {}
    for record_set in RECORD_SETS:
        path = SOURCE_ROOT / record_set / PROTOCOL / "collapse_observations.csv"
        if not path.exists():
            raise FileNotFoundError(f"Missing Sensitivity v3 observations: {path}")
        df = pd.read_csv(path)
        required = {"specimen_id", "gm_id", "im_observation", "censored"}
        missing = sorted(required - set(df.columns))
        if missing:
            raise ValueError(f"{path} missing required columns: {missing}")
        df["record_set"] = record_set
        data[record_set] = df.copy()
    return data


def _fit_subset(subset_id: int, record_set: str, obs: pd.DataFrame) -> FitRow:
    fit = fit_lognormal_capacity_censored_mle(
        obs["im_observation"].to_numpy(dtype=float),
        obs["censored"].to_numpy(dtype=bool),
    )
    return FitRow(
        subset_id=subset_id,
        record_set=record_set,
        theta=float(fit.theta),
        beta=float(fit.beta),
        mu=float(fit.mu),
        n_total=int(fit.n_total),
        n_observed=int(fit.n_observed),
        n_censored=int(fit.n_censored),
        log_likelihood=float(fit.log_likelihood),
    )


def _sample_record_bootstrap(
    data: dict[str, pd.DataFrame],
    *,
    b: int,
    records_per_pool: int,
    seed: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    manifest_rows: list[dict[str, object]] = []
    fit_rows: list[FitRow] = []

    for subset_id in range(b):
        for record_set in RECORD_SETS:
            obs = data[record_set]
            gm_ids = np.array(sorted(obs["gm_id"].astype(str).unique()))
            if len(gm_ids) < records_per_pool:
                raise ValueError(
                    f"{record_set} has only {len(gm_ids)} completed records; "
                    f"cannot draw {records_per_pool} records."
                )
            draw = rng.choice(gm_ids, size=records_per_pool, replace=True)
            chunks = []
            for draw_order, gm_id in enumerate(draw):
                part = obs[obs["gm_id"].astype(str) == str(gm_id)].copy()
                part["bootstrap_draw_order"] = draw_order
                part["bootstrap_gm_id"] = str(gm_id)
                part["bootstrap_occurrence"] = int(np.sum(draw[: draw_order + 1] == gm_id))
                chunks.append(part)
                manifest_rows.append(
                    {
                        "subset_id": subset_id,
                        "record_set": record_set,
                        "draw_order": draw_order,
                        "gm_id": str(gm_id),
                    }
                )
            subset_obs = pd.concat(chunks, ignore_index=True)
            fit_rows.append(_fit_subset(subset_id, record_set, subset_obs))

    manifest = pd.DataFrame(manifest_rows)
    fits = pd.DataFrame([asdict(r) for r in fit_rows])
    return manifest, fits


def _make_effect_distribution(fits: pd.DataFrame) -> pd.DataFrame:
    wide_theta = fits.pivot(index="subset_id", columns="record_set", values="theta")
    wide_beta = fits.pivot(index="subset_id", columns="record_set", values="beta")
    rows = []
    for contrast in ["FFext", "NF28"]:
        delta = np.log(wide_theta[contrast] / wide_theta["FF22"])
        rows.append(
            pd.DataFrame(
                {
                    "subset_id": wide_theta.index,
                    "contrast": f"{contrast}_vs_FF22",
                    "theta_ref": wide_theta["FF22"].to_numpy(),
                    "theta_contrast": wide_theta[contrast].to_numpy(),
                    "beta_ref": wide_beta["FF22"].to_numpy(),
                    "beta_contrast": wide_beta[contrast].to_numpy(),
                    "delta_logtheta": delta.to_numpy(),
                    "theta_percent_shift": (np.exp(delta.to_numpy()) - 1.0) * 100.0,
                    "psi": np.abs(delta.to_numpy()) / 2.0,
                }
            )
        )
    return pd.concat(rows, ignore_index=True)


def _summarize_effects(effects: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for contrast, g in effects.groupby("contrast", sort=True):
        delta = g["delta_logtheta"].to_numpy(dtype=float)
        psi = g["psi"].to_numpy(dtype=float)
        rows.append(
            {
                "contrast": contrast,
                "B": int(len(g)),
                "median_delta_logtheta": float(np.median(delta)),
                "q05_delta_logtheta": float(np.quantile(delta, 0.05)),
                "q95_delta_logtheta": float(np.quantile(delta, 0.95)),
                "p_delta_logtheta_lt_0": float(np.mean(delta < 0.0)),
                "median_theta_percent_shift": float((np.exp(np.median(delta)) - 1.0) * 100.0),
                "q05_theta_percent_shift": float((np.exp(np.quantile(delta, 0.05)) - 1.0) * 100.0),
                "q95_theta_percent_shift": float((np.exp(np.quantile(delta, 0.95)) - 1.0) * 100.0),
                "median_psi": float(np.median(psi)),
                "interpretation": _interpret(delta),
            }
        )
    return pd.DataFrame(rows)


def _interpret(delta: np.ndarray) -> str:
    q05, q95 = np.quantile(delta, [0.05, 0.95])
    p_neg = float(np.mean(delta < 0.0))
    if q95 < 0.0:
        return "direction_stable_negative_in_existing_record_bootstrap"
    if q05 > 0.0:
        return "direction_stable_positive_in_existing_record_bootstrap"
    if 0.1 < p_neg < 0.9:
        return "sign_sensitive_under_existing_record_bootstrap"
    return "mostly_one_sided_but_interval_touches_zero"


def _plot_outputs(fits: pd.DataFrame, effects: pd.DataFrame) -> None:
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    MANUSCRIPT_FIG_DIR.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    for record_set, color in zip(RECORD_SETS, ["#4C78A8", "#F58518", "#54A24B"]):
        x = fits[fits["record_set"] == record_set]["theta"].to_numpy(dtype=float)
        ax.hist(x, bins=30, alpha=0.45, density=True, label=record_set, color=color)
    ax.set_xlabel(r"Bootstrapped median capacity $\theta$ (g)")
    ax.set_ylabel("Density")
    ax.set_title("R1 existing-record bootstrap: fitted capacity distributions")
    ax.grid(True, alpha=0.25)
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "fig_r1_theta_distribution.png", dpi=300, bbox_inches="tight")
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    for contrast, color in zip(["FFext_vs_FF22", "NF28_vs_FF22"], ["#F58518", "#54A24B"]):
        x = effects[effects["contrast"] == contrast]["delta_logtheta"].to_numpy(dtype=float)
        ax.hist(x, bins=30, alpha=0.5, density=True, label=contrast, color=color)
    ax.axvline(0.0, color="black", linewidth=1.0)
    ax.set_xlabel(r"$\Delta \log \theta$ relative to FF22")
    ax.set_ylabel("Density")
    ax.set_title("R1 existing-record bootstrap: record-pool contrasts")
    ax.grid(True, alpha=0.25)
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "fig_r1_delta_logtheta_distribution.png", dpi=300, bbox_inches="tight")
    fig.savefig(MANUSCRIPT_FIG_DIR / "fig12_r1_delta_logtheta_distribution.png", dpi=300, bbox_inches="tight")
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    for contrast, color in zip(["FFext_vs_FF22", "NF28_vs_FF22"], ["#F58518", "#54A24B"]):
        x = effects[effects["contrast"] == contrast]["psi"].to_numpy(dtype=float)
        ax.hist(x, bins=30, alpha=0.5, density=True, label=contrast, color=color)
    ax.set_xlabel(r"Study-specific $PSI=|\Delta\log\theta|/2$")
    ax.set_ylabel("Density")
    ax.set_title("R1 existing-record bootstrap: PSI distributions")
    ax.grid(True, alpha=0.25)
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "fig_r1_psi_distribution.png", dpi=300, bbox_inches="tight")
    plt.close(fig)


def _write_note(summary: pd.DataFrame, b: int, records_per_pool: int, seed: int) -> None:
    lines = [
        "# R1 Existing-Record Bootstrap Summary",
        "",
        f"Bootstrap draws: B={b}; records per pool per draw={records_per_pool}; seed={seed}.",
        "",
        "This is a record-level bootstrap over the completed Sensitivity v3 matrix. It reuses real",
        "OpenSees-derived collapse observations and therefore does not add new ground motions beyond",
        "the ten completed records per pool. It is a screening analysis for record-subset stability,",
        "not a substitute for a full repeated OpenSees subset-resampling matrix over the broader pools.",
        "",
        "| Contrast | B | median delta_logtheta | 5% | 95% | P(delta_logtheta < 0) | median PSI | Interpretation |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for _, row in summary.iterrows():
        lines.append(
            f"| {row['contrast']} | {int(row['B'])} | {row['median_delta_logtheta']:.3f} | "
            f"{row['q05_delta_logtheta']:.3f} | {row['q95_delta_logtheta']:.3f} | "
            f"{row['p_delta_logtheta_lt_0']:.3f} | {row['median_psi']:.3f} | "
            f"{row['interpretation']} |"
        )
    lines.extend(
        [
            "",
            "Gate interpretation:",
            "",
            "- If a contrast's 5-95% interval crosses zero, the manuscript must not report a stable directional shift for that contrast.",
            "- If the interval is one-sided under this screening bootstrap, the manuscript may describe it as stable within the completed ten-record Sensitivity v3 set, not as production-scale evidence.",
        ]
    )
    (OUT_ROOT / "r1_existing_record_bootstrap_note.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    b = DEFAULT_B
    records_per_pool = DEFAULT_RECORDS_PER_POOL
    seed = DEFAULT_SEED

    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    data = _load_observations()
    manifest, fits = _sample_record_bootstrap(data, b=b, records_per_pool=records_per_pool, seed=seed)
    effects = _make_effect_distribution(fits)
    summary = _summarize_effects(effects)

    manifest.to_csv(OUT_ROOT / "r1_subset_manifest.csv", index=False)
    fits.to_csv(OUT_ROOT / "r1_censored_mle_by_subset.csv", index=False)
    effects.to_csv(OUT_ROOT / "r1_protocol_effect_distribution.csv", index=False)
    summary.to_csv(OUT_ROOT / "r1_summary_table.csv", index=False)
    _plot_outputs(fits, effects)
    _write_note(summary, b=b, records_per_pool=records_per_pool, seed=seed)
    print(summary.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
