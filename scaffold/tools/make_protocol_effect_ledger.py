from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


SUMMARY_PATH = Path("data/expanded_pilot_v2/figures/expanded_pilot_v2_summary.csv")
OUT_DIR = Path("data/expanded_pilot_v2/figures")
DOC_DIR = Path("docs/manuscript_drafts")


def build_protocol_effect_ledger(summary: pd.DataFrame, *, reference: str = "FF22", protocol: str = "P1") -> pd.DataFrame:
    """Build an auditable record-pool effect ledger in log-capacity units."""
    d = summary[summary["protocol"] == protocol].copy()
    if reference not in set(d["record_set"]):
        raise ValueError(f"Reference record set not found: {reference}")

    ref = d[d["record_set"] == reference].iloc[0]
    theta_ref = float(ref["theta"])
    beta_ref = float(ref["beta"])

    rows = []
    for _, row in d.sort_values("record_set").iterrows():
        theta = float(row["theta"])
        beta = float(row["beta"])
        log_shift = float(np.log(theta / theta_ref))
        percent_shift = 100.0 * (theta - theta_ref) / theta_ref
        # FEMA-style binary spread convention: two endpoint medians correspond to +/- 1 sigma.
        beta_pool_equiv = abs(log_shift) / 2.0
        rows.append(
            {
                "effect_family": "record_pool",
                "reference_record_set": reference,
                "record_set": row["record_set"],
                "protocol": protocol,
                "theta_ref": theta_ref,
                "theta": theta,
                "theta_percent_shift_vs_ref": percent_shift,
                "log_theta_shift_vs_ref": log_shift,
                "beta_pool_equiv_binary": beta_pool_equiv,
                "beta_ref": beta_ref,
                "beta": beta,
                "beta_shift_vs_ref": beta - beta_ref,
                "censoring_rate": float(row["censoring_rate"]),
                "n_runs": int(row["n_runs"]),
                "n_nonconverged": int(row["n_nonconverged"]),
                "interpretation": _interpret_effect(row["record_set"], percent_shift, beta_pool_equiv),
            }
        )
    return pd.DataFrame(rows)


def _interpret_effect(record_set: str, percent_shift: float, beta_pool_equiv: float) -> str:
    if record_set == "FF22":
        return "reference"
    if abs(percent_shift) >= 30:
        size = "large"
    elif abs(percent_shift) >= 10:
        size = "moderate"
    else:
        size = "small"
    return f"{size} record-pool effect; beta_pool_equiv={beta_pool_equiv:.3f}"


def write_note(ledger: pd.DataFrame) -> None:
    DOC_DIR.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Protocol-Effect Ledger Note",
        "",
        "This note converts Expanded Pilot v2 record-pool shifts into auditable log-capacity units.",
        "It is not a new fragility fit; it is an interpretation layer over `expanded_pilot_v2_summary.csv`.",
        "",
        "## Record-Pool Effects",
        "",
    ]
    for _, row in ledger.iterrows():
        lines.append(
            f"- {row['record_set']} vs {row['reference_record_set']}: "
            f"theta shift = {row['theta_percent_shift_vs_ref']:+.1f}%, "
            f"log shift = {row['log_theta_shift_vs_ref']:+.3f}, "
            f"binary-equivalent beta_pool = {row['beta_pool_equiv_binary']:.3f}."
        )
    lines.extend(
        [
            "",
            "## Manuscript Use",
            "",
            "Use this ledger to avoid treating record-pool choice as a qualitative implementation detail.",
            "The current evidence supports `beta_pool` as the first computed component of a broader protocol-effect uncertainty ledger.",
            "Future iterations should add `beta_grid`, `beta_rule`, `beta_num`, and possibly `beta_CV` if ML capacity priors are imported from Paper A.",
        ]
    )
    (DOC_DIR / "protocol_effect_ledger_note.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    summary = pd.read_csv(SUMMARY_PATH)
    ledger = build_protocol_effect_ledger(summary, reference="FF22", protocol="P1")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ledger.to_csv(OUT_DIR / "protocol_effect_ledger.csv", index=False)
    write_note(ledger)
    print(f"Wrote protocol effect ledger to {OUT_DIR / 'protocol_effect_ledger.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

