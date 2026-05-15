from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def plot_ida_stripes(enriched_csv: Path, out_png: Path) -> None:
    df = pd.read_csv(enriched_csv)
    # plot each (specimen, gm) curve: IM vs drift ratio, mark first crossing
    fig, ax = plt.subplots(figsize=(7.5, 4.5))
    for (specimen_id, gm_id), g in df.groupby(["specimen_id", "gm_id"], sort=False):
        g = g.sort_values("im_value")
        ax.plot(g["im_value"], g["edp_max_drift_ratio"], alpha=0.8, lw=1.6, label=f"{specimen_id}-{gm_id}")
        fc = g[g["first_crossing"].astype(bool)]
        if len(fc) > 0:
            ax.scatter(fc["im_value"], fc["edp_max_drift_ratio"], s=35)
    ax.set_xlabel("IM (g)")
    ax.set_ylabel("Max drift ratio")
    ax.grid(True, alpha=0.25)
    ax.legend(loc="best", fontsize=8, frameon=False)
    fig.tight_layout()
    fig.savefig(out_png, dpi=200)
    plt.close(fig)


def plot_censored_summary(mle_csv: Path, out_png: Path) -> None:
    df = pd.read_csv(mle_csv)
    # keep ALL + mech groups with finite theta
    df = df[df["group"].str.contains("ALL|MECH::", regex=True)].copy()
    fig, ax = plt.subplots(figsize=(7.5, 3.8))
    x = np.arange(len(df))
    ax.bar(x, df["theta"].fillna(0.0), color="#4C78A8")
    ax.set_xticks(x)
    ax.set_xticklabels(df["group"], rotation=25, ha="right")
    ax.set_ylabel("Median capacity θ (g)")
    ax.grid(True, axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(out_png, dpi=200)
    plt.close(fig)


def main() -> int:
    demo_dir = Path("data/demo")
    fig_dir = Path("data/demo/figures")
    _ensure_dir(fig_dir)

    enriched = demo_dir / "ida_raw_all_enriched.csv"
    mle = demo_dir / "censored_mle_summary.csv"
    if not enriched.exists() or not mle.exists():
        raise SystemExit("Missing demo outputs. Run tools/demo_run_pipeline.py first.")

    plot_ida_stripes(enriched, fig_dir / "fig_ida_stripes_demo.png")
    plot_censored_summary(mle, fig_dir / "fig_mle_theta_demo.png")
    print("Wrote:", fig_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

